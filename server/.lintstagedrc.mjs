export default {
  '*.py': ['uv run ruff check --fix', 'uv run ruff format'],
  'pyproject.toml': () => 'uv lock --check',
};
