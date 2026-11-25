// Optional evaluator extension. Only these three task-specific tools may execute.
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { spawn } from "node:child_process";
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";

export default function trialGuard(api: ExtensionAPI) {
    const root = process.env.TRIAL_ROOT;
    const nonce = process.env.TRIAL_NONCE;
    const python = process.env.TRIAL_PYTHON;
    const boundary = process.env.TRIAL_BOUNDARY;
    if (!root || !nonce || !/^[a-f0-9]{48}$/.test(nonce) || !python || !boundary) {
        throw new Error("Trial guard requires a runner-issued root, nonce and Python boundary");
    }
    const canonicalRoot = fs.realpathSync(root);
    if (path.resolve(root) !== canonicalRoot || fs.lstatSync(root).isSymbolicLink()) {
        throw new Error("Trial workspace must not be a symlink/junction");
    }
    const localOnly = process.env.TRIAL_LOCAL_ONLY === "1";
    const skill = ".agents/skills/yeet/SKILL.md";
    const fixtures = ["test_names.py", "test_dates.py"].filter(name => fs.existsSync(path.join(root, name)));
    if ((!localOnly && fixtures.length !== 1) || (localOnly && fixtures.length !== 0)) {
        throw new Error("Ambiguous task: require exactly one coding fixture or a fixture-free blocked task");
    }
    const fixture = localOnly ? undefined : fixtures[0];
    const source = fixture === "test_names.py" ? "names.py" : "sort_dates.py";
    // Hill-climb task: local-only, the named file is missing; project notes point to its new home.
    const hill = localOnly && fs.existsSync(path.join(root, "README.md"));
    const readable = new Set(hill ? [skill, "config.json", "README.md", "NOTES.md", "settings/app.json", "REPORT.md"]
        : localOnly ? [skill, "release-input.md", "RELEASE.md"] : [skill, fixture!, source]);
    const writable = new Set(hill ? ["REPORT.md"] : localOnly ? ["RELEASE.md"] : [source]);
    const allowedTools = new Set(localOnly ? ["trial_read", "trial_write"] : ["trial_read", "trial_write", "trial_check"]);
    const maxBytes = 256 * 1024;
    let checking = false;

    function target(value: unknown, allowed: Set<string>, missing = false): string {
        // Exact spelling checked BEFORE normalisation/resolution/open. This excludes
        // URI, UNC/device, absolute, ADS, traversal, backslash and Win32 aliases.
        if (typeof value !== "string" || !allowed.has(value) || value.includes("\\") || value.includes(":") ||
            value.startsWith("/") || value.split("/").some(p => p === "." || p === ".." || !p)) {
            throw new Error("Trial path denied: use an exact allowed relative path");
        }
        let current = root!;
        const parts = value.split("/");
        for (let index = 0; index < parts.length; index++) {
            current = path.join(current, parts[index]);
            try {
                const stat = fs.lstatSync(current);
                if (stat.isSymbolicLink() || (stat.isFile() && stat.nlink !== 1)) {
                    throw new Error("Trial symlinks/junctions/hardlinks denied");
                }
                if (index < parts.length - 1 && !stat.isDirectory()) throw new Error("Trial parent is not a directory");
                if (index === parts.length - 1 && !stat.isFile()) throw new Error("Trial target is not a regular file");
                if (fs.realpathSync(current) !== current) throw new Error("Trial path alias denied");
            } catch (error: unknown) {
                if (!(missing && index === parts.length - 1 && error instanceof Error && "code" in error && error.code === "ENOENT")) throw error;
            }
        }
        return current;
    }

    const digest = (data: Buffer) => crypto.createHash("sha256").update(data).digest("hex");
    const originalFixture = fixture ? fs.readFileSync(target(fixture, readable)) : undefined;
    const fixtureHash = originalFixture ? digest(originalFixture) : undefined;
    const reply = (text: string, details: unknown) => ({ content: [{ type: "text", text }], details });
    const z = api.zod;

    // OMP's documented pre-execution tool_call veto uses {block:true,reason}.
    // Never delegate to a tool based on a URI, alias or model-supplied command.
    api.on("tool_call", (event) => {
        if (!allowedTools.has(event.toolName)) return { block: true, reason: "Trial guard denied non-trial tool before execution" };
        try {
            if (checking) throw new Error("Trial check in progress; concurrent tools denied");
            if (event.toolName === "trial_read") target(event.input.path, readable);
            if (event.toolName === "trial_write") target(event.input.path, writable, true);
            if (event.toolName === "trial_check" && Object.keys(event.input).length !== 0) throw new Error("trial_check accepts no arguments");
        } catch (error) {
            return { block: true, reason: String(error) };
        }
    });

    api.registerTool({
        name: "trial_read", label: "Trial read", loadMode: "essential", approval: "read",
        description: "Read an exact allowed relative task path, including .agents/skills/yeet/SKILL.md; no URIs or outside paths.",
        parameters: z.object({ path: z.string() }).strict(),
        async execute(_id: string, args: {path: string}) {
            if (checking) throw new Error("Trial check in progress");
            const data = fs.readFileSync(target(args.path, readable));
            if (data.length > maxBytes) throw new Error("Trial read exceeds 256 KiB");
            return reply(data.toString("utf8"), { path: args.path, bytes: data.length, sha256: digest(data) });
        }
    });
    api.registerTool({
        name: "trial_write", label: "Trial write", loadMode: "essential", approval: "write",
        description: `Write only ${[...writable].join(", ")}; whole UTF-8 file, no fixture changes.`,
        parameters: z.object({ path: z.string(), content: z.string() }).strict(),
        async execute(_id: string, args: {path: string, content: string}) {
            if (checking) throw new Error("Trial check in progress");
            const data = Buffer.from(args.content, "utf8");
            if (data.length > maxBytes) throw new Error("Trial write exceeds 256 KiB");
            const filename = target(args.path, writable, true);
            // No executing process may run concurrently with a read/write/check call.
            fs.writeFileSync(filename, data);
            const actual = fs.readFileSync(target(args.path, writable));
            return reply(actual.toString("utf8"), { path: args.path, bytes: actual.length, sha256: digest(actual) });
        }
    });
    if (fixture) api.registerTool({
        name: "trial_check", label: "Trial check", loadMode: "essential", approval: "exec",
        description: `Execute the immutable original ${fixture} in network-disabled Windows MXC. No code or command arguments.`,
        parameters: z.object({}).strict(),
        async execute(_id: string, args: Record<string, never>, signal: AbortSignal | undefined) {
            if (checking) throw new Error("Trial check already in progress");
            checking = true;
            try {
            if (Object.keys(args).length) throw new Error("trial_check accepts no arguments");
            if (!fs.readFileSync(target(fixture, readable)).equals(originalFixture!)) throw new Error("Immutable fixture changed");
            const childEnv = z.record(z.string(), z.string()).parse(JSON.parse(process.env.TRIAL_CHILD_ENV || "null"));
            // This trusted helper is outside the workspace and Python -I excludes
            // cwd/user paths while loading it. Only python_process executes trial code.
            const child = spawn(python, ["-I", "-B", "-X", "utf8", boundary, "--check", root!, fixture, fixtureHash!],
                { cwd: path.dirname(boundary), env: childEnv, windowsHide: true, stdio: ["ignore", "pipe", "pipe"], signal });
            const chunks: Buffer[] = [], errors: Buffer[] = [];
            let size = 0;
            let exceeded = false;
            const collect = (list: Buffer[]) => (chunk: Buffer) => {
                size += chunk.length;
                if (size > 1024 * 1024) { exceeded = true; child.kill(); }
                else list.push(chunk);
            };
            child.stdout.on("data", collect(chunks));
            child.stderr.on("data", collect(errors));
            const { promise, resolve, reject } = Promise.withResolvers<number | null>();
            child.on("error", reject);
            child.on("close", resolve);
            const status = await promise;
            if (exceeded) throw new Error("Trial check output limit exceeded");
            if (status !== 0) throw new Error(`Trial boundary exited ${status}: ${Buffer.concat(errors).toString("utf8")}`);
            const result = z.object({
                fixture: z.literal(fixture), exitCode: z.number().int(), completed: z.boolean(),
                stdout: z.string(), stderr: z.string()
            }).strict().parse(JSON.parse(Buffer.concat(chunks).toString("utf8")));
            if (!fs.readFileSync(target(fixture, readable)).equals(originalFixture!)) throw new Error("Fixture changed during check");
            const passed = result.exitCode === 0 && result.completed;
            // Visible verdict: a bare completion marker reads as an opaque, broken tool result.
            const verdict = `${fixture}: ${passed ? "PASS" : "FAIL"} (exit ${result.exitCode}, ${result.completed ? "completed" : "incomplete"})\n`;
            return { ...reply(verdict + result.stdout + result.stderr, { fixture, exitCode: result.exitCode, completed: result.completed }),
                     isError: !passed };
            } finally {
                checking = false;
            }
        }
    });

    // Readiness comes LAST: a load failure cannot mint this per-process command.
    api.registerCommand("trial_guard_" + nonce, {
        description: "Trial boundary registered; runner-only nonce handshake",
        handler: async () => { throw new Error("Readiness command is not a model tool"); }
    });
}
