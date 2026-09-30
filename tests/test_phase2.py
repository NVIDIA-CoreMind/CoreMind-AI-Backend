"""
Tests for Phase 2: Symbols, RepoMap, Hybrid Search, Project Rules, Compactor.
"""

from pathlib import Path

from src.context.compactor import compress_tool_output
from src.context.rules import load_project_rules
from src.project.repo_map import RepoMap
from src.project.search import HybridCodeSearcher
from src.project.symbols import extract_dart_symbols, extract_python_symbols, extract_ts_symbols


class TestSymbolExtraction:
    """Test multi-language symbol extraction."""

    def test_extract_python_symbols(self) -> None:
        code = '''
class AuthController:
    """Handles authentication."""

    def login(self, username, password):
        """Perform login."""
        return True

def standalone_helper(x, y):
    return x + y
'''
        symbols = extract_python_symbols(code, "auth.py")
        assert len(symbols) == 2
        cls_sym = symbols[0]
        assert cls_sym.name == "AuthController"
        assert cls_sym.kind == "class"
        assert len(cls_sym.children) == 1
        assert cls_sym.children[0].name == "login"

        fn_sym = symbols[1]
        assert fn_sym.name == "standalone_helper"
        assert fn_sym.kind == "function"

    def test_extract_dart_symbols(self) -> None:
        code = '''
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Container();
  }
}
'''
        symbols = extract_dart_symbols(code, "login_screen.dart")
        assert len(symbols) >= 1
        cls_sym = symbols[0]
        assert cls_sym.name == "LoginScreen"
        assert cls_sym.kind == "class"

    def test_extract_ts_symbols(self) -> None:
        code = '''
export interface UserPayload {
  id: string;
  email: string;
}

export class AuthService {
  async authenticate(token: string) {
    return true;
  }
}

export function verifyToken(raw: string) {
  return raw.length > 0;
}
'''
        symbols = extract_ts_symbols(code, "auth.ts")
        names = [s.name for s in symbols]
        assert "UserPayload" in names
        assert "AuthService" in names
        assert "verifyToken" in names


class TestRepoMap:
    """Test RepoMap generator."""

    def test_build_compact_summary(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "service.py").write_text("class MyService:\n    def do_work(self):\n        pass\n")

        repo_map = RepoMap(str(tmp_path))
        summary = repo_map.build_compact_summary()
        assert "## Repository Map" in summary
        assert "service.py" in summary
        assert "class MyService" in summary


class TestHybridSearch:
    """Test exact, symbol, and semantic search."""

    def test_hybrid_search(self, tmp_path: Path) -> None:
        src = tmp_path / "auth"
        src.mkdir()
        (src / "login.py").write_text("class AuthManager:\n    def handle_login(self):\n        pass\n")
        (src / "notes.txt").write_text("Where is authentication handled? Look into AuthManager.\n")

        searcher = HybridCodeSearcher(str(tmp_path))
        results = searcher.search("authentication")
        assert len(results) > 0
        matches_text = " ".join(r.content for r in results)
        assert "AuthManager" in matches_text or "authentication" in matches_text


class TestProjectRules:
    """Test project rules detection."""

    def test_load_project_rules(self, tmp_path: Path) -> None:
        rules_file = tmp_path / ".coremindrules"
        rules_file.write_text("- Always use clean architecture.\n- Do not use print statements.\n")

        rules = load_project_rules(str(tmp_path))
        assert "Project-Specific Rules" in rules
        assert "Always use clean architecture" in rules


class TestToolOutputCompactor:
    """Test tool output compression."""

    def test_compress_large_output(self) -> None:
        raw_output = "\n".join([f"Building package step {i}..." for i in range(100)])
        raw_output += "\nError: lib/main.dart:45: Undefined name 'loginWidget'\n"
        raw_output += "\n".join([f"Finishing build step {i}..." for i in range(50)])

        compressed = compress_tool_output("terminal", raw_output, max_lines=25)
        assert "Output compressed" in compressed
        assert "Undefined name 'loginWidget'" in compressed
