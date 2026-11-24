"""Validate yeet's portable package. Not a behavioural evaluator."""
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
IGNORED = {'.git', 'node_modules', '__pycache__', '.venv', 'trial-results'}
REQUIRED = {
    'Contract': ('outcome', 'scope', 'constraints', 'checks', 'read-only'),
    'Act': ('one owner', 'ten consecutive cycles', 'two attempts', 'integrate', 'regression'),
    'Permission': ('exact target', 'approval', 'read back', 'credentials', 'provider safety'),
    'Verify and finish': ('fresh check', 'actual UI', 'missing required'),
    'Words': ('sacrifice grammar, not meaning', 'one term per concept', 'uncertainty'),
}


def files(root):
    for child in root.iterdir():
        if child.name in IGNORED:
            continue
        if child.is_symlink():
            raise ValueError(f'Symlink not portable: {child.relative_to(ROOT)}')
        if child.is_dir():
            yield from files(child)
        elif child.is_file():
            yield child


def validate():
    errors = []
    paths = list(files(ROOT))
    skills = [p.relative_to(ROOT).as_posix() for p in paths if p.name == 'SKILL.md']
    if skills != ['skills/yeet/SKILL.md']:
        errors.append(f'Expected one skill: {skills}')
    skill = ROOT / 'skills/yeet/SKILL.md'
    text = skill.read_text(encoding='utf-8')
    match = re.match(r'\A---\nname: yeet\ndescription: "([^"\\\n]+)"\n---\n', text)
    if not match or len(match.group(1)) > 1024:
        errors.append('Invalid name/description frontmatter')
    if len(text.split()) > 1300:
        errors.append('Skill exceeds 1,300-word context budget')
    sections = dict(re.findall(r'^## ([^\n]+)\n(.*?)(?=^## |\Z)', text, re.M | re.S))
    for title, phrases in REQUIRED.items():
        if title not in sections:
            errors.append(f'Missing section: {title}')
        body = sections.get(title, '').casefold()
        for phrase in phrases:
            # Coverage check only: wording presence cannot prove obedience.
            if phrase.casefold() not in body:
                errors.append(f'Missing rule coverage: {title}: {phrase}')
    adapter = (ROOT / 'skills/yeet/agents/openai.yaml').read_text(encoding='utf-8')
    adapter_pattern = (
        r'interface:\n  display_name: "yeet"\n'
        r'  short_description: "[^"\\\n]{1,64}"\n'
        r'  default_prompt: "Use \$yeet[^"\\\n]*"\n'
        r'policy:\n  allow_implicit_invocation: true\n'
    )
    if not re.fullmatch(adapter_pattern, adapter):
        errors.append('Invalid adapter schema or implicit invocation policy')
    allowed_roots = {'AGENTS.md', 'README.md', 'LICENSE', 'CREDITS.md', 'CHANGELOG.md',
                     '.gitignore', '.gitattributes', 'skills', 'tools', '.github'}
    for path in paths:
        relative = path.relative_to(ROOT)
        if relative.parts[0] not in allowed_roots:
            errors.append(f'Legacy or unexpected file: {relative}')
        if path.suffix == '.md':
            content = path.read_text(encoding='utf-8')
            for link in re.findall(r'(?<!!)\[[^\]]*\]\(([^\s)]+)\)', content):
                url = urlsplit(link)
                if url.scheme or url.netloc or not url.path:
                    continue
                target = (path.parent / unquote(url.path)).resolve()
                if not target.is_relative_to(ROOT) or not target.exists():
                    errors.append(f'Broken/outside local link: {relative}: {link}')
    if errors:
        print('\n'.join(f'FAIL: {e}' for e in errors), file=sys.stderr)
        return 1
    print(f'PASS: one yeet skill; {len(text.split())} words; metadata, links and rule coverage')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(validate())
    except (OSError, ValueError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        sys.exit(1)
