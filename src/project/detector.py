"""
CoreMind Backend — Project Detector.

Detects project language, framework, and configuration by inspecting
well-known config files (package.json, pubspec.yaml, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProjectInfo:
    """Detected project metadata."""

    language: str
    framework: str
    package_manager: str
    main_entry: str
    test_command: str
    config_file: str


# Detection rules ordered by priority
_DETECTION_RULES: list[tuple[str, ProjectInfo]] = [
    (
        "pubspec.yaml",
        ProjectInfo(
            language="Dart",
            framework="Flutter",
            package_manager="pub",
            main_entry="lib/main.dart",
            test_command="flutter test",
            config_file="pubspec.yaml",
        ),
    ),
    (
        "package.json",
        ProjectInfo(
            language="TypeScript/JavaScript",
            framework="Node.js",
            package_manager="npm",
            main_entry="src/index.ts",
            test_command="npm test",
            config_file="package.json",
        ),
    ),
    (
        "pyproject.toml",
        ProjectInfo(
            language="Python",
            framework="Python",
            package_manager="pip",
            main_entry="src/main.py",
            test_command="pytest",
            config_file="pyproject.toml",
        ),
    ),
    (
        "requirements.txt",
        ProjectInfo(
            language="Python",
            framework="Python",
            package_manager="pip",
            main_entry="main.py",
            test_command="pytest",
            config_file="requirements.txt",
        ),
    ),
    (
        "Cargo.toml",
        ProjectInfo(
            language="Rust",
            framework="Rust",
            package_manager="cargo",
            main_entry="src/main.rs",
            test_command="cargo test",
            config_file="Cargo.toml",
        ),
    ),
    (
        "go.mod",
        ProjectInfo(
            language="Go",
            framework="Go",
            package_manager="go",
            main_entry="main.go",
            test_command="go test ./...",
            config_file="go.mod",
        ),
    ),
    (
        "pom.xml",
        ProjectInfo(
            language="Java",
            framework="Maven",
            package_manager="maven",
            main_entry="src/main/java",
            test_command="mvn test",
            config_file="pom.xml",
        ),
    ),
    (
        "build.gradle",
        ProjectInfo(
            language="Java/Kotlin",
            framework="Gradle",
            package_manager="gradle",
            main_entry="src/main/java",
            test_command="gradle test",
            config_file="build.gradle",
        ),
    ),
    (
        "CMakeLists.txt",
        ProjectInfo(
            language="C/C++",
            framework="CMake",
            package_manager="cmake",
            main_entry="src/main.cpp",
            test_command="ctest",
            config_file="CMakeLists.txt",
        ),
    ),
    (
        "composer.json",
        ProjectInfo(
            language="PHP",
            framework="PHP",
            package_manager="composer",
            main_entry="public/index.php",
            test_command="vendor/bin/phpunit",
            config_file="composer.json",
        ),
    ),
]


def detect_project(project_path: str) -> ProjectInfo:
    """Detect the project type by inspecting config files."""
    root = Path(project_path)

    for config_file, info in _DETECTION_RULES:
        if (root / config_file).exists():
            # Refine detection for package.json
            if config_file == "package.json":
                return _refine_node_project(root, info)
            return info

    return ProjectInfo(
        language="Unknown",
        framework="Unknown",
        package_manager="Unknown",
        main_entry="",
        test_command="",
        config_file="",
    )


def _refine_node_project(root: Path, base: ProjectInfo) -> ProjectInfo:
    """Refine Node.js project detection (Next.js, React, etc.)."""
    try:
        content = (root / "package.json").read_text()

        if '"next"' in content:
            return ProjectInfo(
                language="TypeScript",
                framework="Next.js",
                package_manager="npm",
                main_entry="src/app/page.tsx",
                test_command="npm test",
                config_file="package.json",
            )
        if '"react"' in content:
            return ProjectInfo(
                language="TypeScript",
                framework="React",
                package_manager="npm",
                main_entry="src/App.tsx",
                test_command="npm test",
                config_file="package.json",
            )
        if '"vue"' in content:
            return ProjectInfo(
                language="TypeScript",
                framework="Vue",
                package_manager="npm",
                main_entry="src/App.vue",
                test_command="npm test",
                config_file="package.json",
            )
    except Exception:
        pass

    return base
