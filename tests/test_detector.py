"""
Tests for the Project Detector.
"""

from pathlib import Path

from src.project.detector import detect_project


class TestProjectDetector:
    """Test project type detection."""

    def test_detect_python_pyproject(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")
        info = detect_project(str(tmp_path))
        assert info.language == "Python"
        assert info.package_manager == "pip"

    def test_detect_flutter(self, tmp_path: Path) -> None:
        (tmp_path / "pubspec.yaml").write_text("name: test_app")
        info = detect_project(str(tmp_path))
        assert info.language == "Dart"
        assert info.framework == "Flutter"

    def test_detect_node(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"name": "test", "dependencies": {}}')
        info = detect_project(str(tmp_path))
        assert "TypeScript" in info.language or "JavaScript" in info.language

    def test_detect_rust(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").write_text("[package]\nname = 'test'")
        info = detect_project(str(tmp_path))
        assert info.language == "Rust"

    def test_detect_go(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text("module test")
        info = detect_project(str(tmp_path))
        assert info.language == "Go"

    def test_detect_unknown(self, tmp_path: Path) -> None:
        info = detect_project(str(tmp_path))
        assert info.language == "Unknown"

    def test_detect_nextjs(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"dependencies": {"next": "14.0.0"}}')
        info = detect_project(str(tmp_path))
        assert info.framework == "Next.js"

    def test_flutter_takes_priority(self, tmp_path: Path) -> None:
        """Flutter (pubspec.yaml) should be detected before package.json."""
        (tmp_path / "pubspec.yaml").write_text("name: test_app")
        (tmp_path / "package.json").write_text('{"name": "test"}')
        info = detect_project(str(tmp_path))
        assert info.framework == "Flutter"

    def test_detect_cmake(self, tmp_path: Path) -> None:
        (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.10)")
        info = detect_project(str(tmp_path))
        assert info.language == "C/C++"
        assert info.framework == "CMake"

    def test_detect_php(self, tmp_path: Path) -> None:
        (tmp_path / "composer.json").write_text('{"name": "test/app"}')
        info = detect_project(str(tmp_path))
        assert info.language == "PHP"

