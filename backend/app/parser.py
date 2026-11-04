"""Source code intelligence and AST parsing engine for Synapse.

Uses Tree-sitter to extract functions, classes, methods, imports, and exports
across multiple programming languages safely without executing code.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from app.schemas import (
    ExtractedSymbol,
    FileParseResult,
    ParseStats,
    RepositoryParseResult,
    SymbolType,
)

# Directories to skip when parsing ASTs to keep performance high
IGNORED_PARSE_DIRS: Set[str] = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".idea",
    ".vscode",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    "vendor",
}

# Maximum file size to parse (1 MB) to avoid memory or CPU spikes
MAX_PARSE_FILE_SIZE = 1_000_000

# Mapping of file extensions to language identifiers
EXTENSION_TO_LANGUAGE: Dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".hh": "cpp",
    ".h": "cpp",
    ".go": "go",
    ".rs": "rust",
}


class TreeSitterGrammarManager:
    """Manages Tree-sitter language grammars and parsers.

    Supports both modern direct packages (e.g. tree_sitter_python)
    and fallback multi-language packages (tree_sitter_languages).
    """

    def __init__(self):
        self._parsers: Dict[str, Any] = {}
        self._languages: Dict[str, Any] = {}
        self._unavailable_languages: Set[str] = set()

    def get_parser(self, language_key: str) -> Optional[Any]:
        """Retrieve or initialize a Tree-sitter Parser for a given language."""
        if language_key in self._unavailable_languages:
            return None

        if language_key in self._parsers:
            return self._parsers[language_key]

        parser = self._create_parser(language_key)
        if parser is not None:
            self._parsers[language_key] = parser
            return parser
        else:
            self._unavailable_languages.add(language_key)
            return None

    def _create_parser(self, language_key: str) -> Optional[Any]:
        """Attempt to instantiate a Tree-sitter parser for a language."""
        try:
            import tree_sitter
        except ImportError:
            return None

        # 1. Try modern individual tree_sitter_<lang> packages
        try:
            lang_instance = None
            if language_key == "python":
                import tree_sitter_python
                lang_instance = tree_sitter.Language(tree_sitter_python.language())
            elif language_key == "javascript":
                import tree_sitter_javascript
                lang_instance = tree_sitter.Language(tree_sitter_javascript.language())
            elif language_key == "typescript":
                import tree_sitter_typescript
                lang_instance = tree_sitter.Language(tree_sitter_typescript.language_typescript())
            elif language_key == "tsx":
                import tree_sitter_typescript
                lang_instance = tree_sitter.Language(tree_sitter_typescript.language_tsx())
            elif language_key == "java":
                import tree_sitter_java
                lang_instance = tree_sitter.Language(tree_sitter_java.language())
            elif language_key == "cpp":
                import tree_sitter_cpp
                lang_instance = tree_sitter.Language(tree_sitter_cpp.language())
            elif language_key == "go":
                import tree_sitter_go
                lang_instance = tree_sitter.Language(tree_sitter_go.language())
            elif language_key == "rust":
                import tree_sitter_rust
                lang_instance = tree_sitter.Language(tree_sitter_rust.language())

            if lang_instance is not None:
                return tree_sitter.Parser(lang_instance)
        except Exception:
            pass

        # 2. Fallback to tree_sitter_languages if available
        try:
            from tree_sitter_languages import get_parser
            key_for_lookup = "typescript" if language_key == "tsx" else language_key
            return get_parser(key_for_lookup)
        except Exception:
            pass

        return None

    def is_language_supported(self, language_key: str) -> bool:
        """Check if grammar is available for the given language key."""
        return self.get_parser(language_key) is not None


_GRAMMAR_MANAGER = TreeSitterGrammarManager()


class ASTSymbolExtractor:
    """Traverses Tree-sitter AST nodes to extract declared symbols."""

    def __init__(self, grammar_manager: Optional[TreeSitterGrammarManager] = None):
        self.grammar_manager = grammar_manager or _GRAMMAR_MANAGER

    def _extract_text(self, node: Any, source_bytes: bytes) -> str:
        """Extract utf-8 decoded text corresponding to a node."""
        try:
            return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace").strip()
        except Exception:
            return ""

    def _extract_parameters(self, params_node: Any, source_bytes: bytes) -> List[str]:
        """Extract parameter names from a parameters node."""
        params: List[str] = []
        if not params_node:
            return params

        for child in params_node.children:
            if child.type in (
                "identifier",
                "typed_parameter",
                "default_parameter",
                "formal_parameter",
                "parameter_declaration",
                "field_declaration",
                "parameter",
            ):
                param_text = self._extract_text(child, source_bytes)
                if param_text and param_text not in (",", "(", ")"):
                    params.append(param_text)
            elif child.type == "spread_element" or child.type == "rest_pattern":
                params.append(self._extract_text(child, source_bytes))

        return params

    def parse_source_code(
        self,
        code_bytes: bytes,
        language_key: str,
        rel_path: str,
    ) -> FileParseResult:
        """Parse source code bytes using the appropriate Tree-sitter grammar."""
        parser = self.grammar_manager.get_parser(language_key)
        if not parser:
            return FileParseResult(
                file_path=rel_path,
                language=language_key,
                errors=[f"Grammar unavailable for language: {language_key}"],
            )

        try:
            tree = parser.parse(code_bytes)
        except Exception as e:
            return FileParseResult(
                file_path=rel_path,
                language=language_key,
                errors=[f"AST parsing exception: {str(e)}"],
            )

        symbols: List[ExtractedSymbol] = []
        warnings: List[str] = []

        if tree.root_node.has_error:
            warnings.append("Syntax errors detected in source file; partial AST extracted.")

        self._traverse_node(
            node=tree.root_node,
            source_bytes=code_bytes,
            language_key=language_key,
            rel_path=rel_path,
            symbols=symbols,
            in_class=None,
        )

        return FileParseResult(
            file_path=rel_path,
            language=language_key,
            symbols=symbols,
            warnings=warnings,
        )

    def _traverse_node(
        self,
        node: Any,
        source_bytes: bytes,
        language_key: str,
        rel_path: str,
        symbols: List[ExtractedSymbol],
        in_class: Optional[str] = None,
    ) -> None:
        """Recursive traversal extracting functions, classes, methods, and imports."""
        node_type = node.type

        # ==================== PYTHON ====================
        if language_key == "python":
            if node_type == "function_definition":
                name_node = node.child_by_field_name("name")
                name = self._extract_text(name_node, source_bytes) if name_node else "anonymous"
                params = self._extract_parameters(node.child_by_field_name("parameters"), source_bytes)
                sym_type = SymbolType.METHOD if in_class else SymbolType.FUNCTION

                symbols.append(
                    ExtractedSymbol(
                        name=f"{in_class}.{name}" if in_class else name,
                        type=sym_type,
                        file_path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        parameters=params,
                        language="python",
                    )
                )

                # Process nested functions or definitions in body
                body_node = node.child_by_field_name("body")
                if body_node:
                    for child in body_node.children:
                        self._traverse_node(child, source_bytes, language_key, rel_path, symbols, in_class=None)
                return

            elif node_type == "class_definition":
                name_node = node.child_by_field_name("name")
                name = self._extract_text(name_node, source_bytes) if name_node else "anonymous_class"
                symbols.append(
                    ExtractedSymbol(
                        name=name,
                        type=SymbolType.CLASS,
                        file_path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        language="python",
                    )
                )
                body_node = node.child_by_field_name("body")
                if body_node:
                    for child in body_node.children:
                        self._traverse_node(child, source_bytes, language_key, rel_path, symbols, in_class=name)
                return

            elif node_type in ("import_statement", "import_from_statement"):
                symbols.append(
                    ExtractedSymbol(
                        name=self._extract_text(node, source_bytes),
                        type=SymbolType.IMPORT,
                        file_path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        language="python",
                    )
                )
                return

        # ==================== JAVASCRIPT / TYPESCRIPT / TSX ====================
        elif language_key in ("javascript", "typescript", "tsx"):
            if node_type == "export_statement":
                # Handle export default or export { ... }
                symbols.append(
                    ExtractedSymbol(
                        name=self._extract_text(node, source_bytes).split("\n")[0][:80],
                        type=SymbolType.EXPORT,
                        file_path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        language=language_key,
                    )
                )
                # Also traverse declaration inside export
                decl = node.child_by_field_name("declaration")
                if decl:
                    self._traverse_node(decl, source_bytes, language_key, rel_path, symbols, in_class=in_class)
                return

            elif node_type == "import_statement":
                symbols.append(
                    ExtractedSymbol(
                        name=self._extract_text(node, source_bytes),
                        type=SymbolType.IMPORT,
                        file_path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        language=language_key,
                    )
                )
                return

            elif node_type in ("function_declaration", "function"):
                name_node = node.child_by_field_name("name")
                name = self._extract_text(name_node, source_bytes) if name_node else "anonymous"
                params = self._extract_parameters(node.child_by_field_name("parameters"), source_bytes)
                symbols.append(
                    ExtractedSymbol(
                        name=name,
                        type=SymbolType.FUNCTION,
                        file_path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        parameters=params,
                        language=language_key,
                    )
                )
                return

            elif node_type == "method_definition":
                name_node = node.child_by_field_name("name")
                name = self._extract_text(name_node, source_bytes) if name_node else "method"
                params = self._extract_parameters(node.child_by_field_name("parameters"), source_bytes)
                symbols.append(
                    ExtractedSymbol(
                        name=f"{in_class}.{name}" if in_class else name,
                        type=SymbolType.METHOD,
                        file_path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        parameters=params,
                        language=language_key,
                    )
                )
                return

            elif node_type in ("class_declaration", "class"):
                name_node = node.child_by_field_name("name")
                name = self._extract_text(name_node, source_bytes) if name_node else "AnonymousClass"
                symbols.append(
                    ExtractedSymbol(
                        name=name,
                        type=SymbolType.CLASS,
                        file_path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        language=language_key,
                    )
                )
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        self._traverse_node(child, source_bytes, language_key, rel_path, symbols, in_class=name)
                return

            elif node_type in ("lexical_declaration", "variable_declaration"):
                for declarator in node.children:
                    if declarator.type == "variable_declarator":
                        name_node = declarator.child_by_field_name("name")
                        val_node = declarator.child_by_field_name("value")
                        if val_node and val_node.type in ("arrow_function", "function_expression"):
                            name = self._extract_text(name_node, source_bytes)
                            params = self._extract_parameters(val_node.child_by_field_name("parameters"), source_bytes)
                            symbols.append(
                                ExtractedSymbol(
                                    name=name,
                                    type=SymbolType.FUNCTION,
                                    file_path=rel_path,
                                    start_line=declarator.start_point[0] + 1,
                                    end_line=declarator.end_point[0] + 1,
                                    parameters=params,
                                    language=language_key,
                                )
                            )

        # ==================== JAVA ====================
        elif language_key == "java":
            if node_type == "import_declaration":
                symbols.append(
                    ExtractedSymbol(
                        name=self._extract_text(node, source_bytes),
                        type=SymbolType.IMPORT,
                        file_path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        language="java",
                    )
                )
                return

            elif node_type in ("class_declaration", "interface_declaration", "enum_declaration"):
                name_node = node.child_by_field_name("name")
                name = self._extract_text(name_node, source_bytes) if name_node else "JavaClass"
                symbols.append(
                    ExtractedSymbol(
                        name=name,
                        type=SymbolType.CLASS,
                        file_path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        language="java",
                    )
                )
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        self._traverse_node(child, source_bytes, language_key, rel_path, symbols, in_class=name)
                return

            elif node_type in ("method_declaration", "constructor_declaration"):
                name_node = node.child_by_field_name("name")
                name = self._extract_text(name_node, source_bytes) if name_node else "method"
                params = self._extract_parameters(node.child_by_field_name("parameters"), source_bytes)
                symbols.append(
                    ExtractedSymbol(
                        name=f"{in_class}.{name}" if in_class else name,
                        type=SymbolType.METHOD if in_class else SymbolType.FUNCTION,
                        file_path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        parameters=params,
                        language="java",
                    )
                )
                return

        # ==================== GO ====================
        elif language_key == "go":
            if node_type == "import_declaration":
                symbols.append(
                    ExtractedSymbol(
                        name=self._extract_text(node, source_bytes),
                        type=SymbolType.IMPORT,
                        file_path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        language="go",
                    )
                )
                return

            elif node_type == "function_declaration":
                name_node = node.child_by_field_name("name")
                name = self._extract_text(name_node, source_bytes) if name_node else "function"
                params = self._extract_parameters(node.child_by_field_name("parameters"), source_bytes)
                symbols.append(
                    ExtractedSymbol(
                        name=name,
                        type=SymbolType.FUNCTION,
                        file_path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        parameters=params,
                        language="go",
                    )
                )
                return

            elif node_type == "method_declaration":
                name_node = node.child_by_field_name("name")
                name = self._extract_text(name_node, source_bytes) if name_node else "method"
                receiver = node.child_by_field_name("receiver")
                recv_text = self._extract_text(receiver, source_bytes) if receiver else ""
                params = self._extract_parameters(node.child_by_field_name("parameters"), source_bytes)
                symbols.append(
                    ExtractedSymbol(
                        name=f"{recv_text}.{name}" if recv_text else name,
                        type=SymbolType.METHOD,
                        file_path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        parameters=params,
                        language="go",
                    )
                )
                return

            elif node_type == "type_declaration":
                for spec in node.children:
                    if spec.type == "type_spec":
                        name_node = spec.child_by_field_name("name")
                        name = self._extract_text(name_node, source_bytes) if name_node else "Type"
                        symbols.append(
                            ExtractedSymbol(
                                name=name,
                                type=SymbolType.CLASS,
                                file_path=rel_path,
                                start_line=spec.start_point[0] + 1,
                                end_line=spec.end_point[0] + 1,
                                language="go",
                            )
                        )
                return

        # ==================== RUST ====================
        elif language_key == "rust":
            if node_type == "use_declaration":
                symbols.append(
                    ExtractedSymbol(
                        name=self._extract_text(node, source_bytes),
                        type=SymbolType.IMPORT,
                        file_path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        language="rust",
                    )
                )
                return

            elif node_type == "function_item":
                name_node = node.child_by_field_name("name")
                name = self._extract_text(name_node, source_bytes) if name_node else "fn"
                params = self._extract_parameters(node.child_by_field_name("parameters"), source_bytes)
                symbols.append(
                    ExtractedSymbol(
                        name=f"{in_class}.{name}" if in_class else name,
                        type=SymbolType.METHOD if in_class else SymbolType.FUNCTION,
                        file_path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        parameters=params,
                        language="rust",
                    )
                )
                return

            elif node_type in ("struct_item", "enum_item", "trait_item"):
                name_node = node.child_by_field_name("name")
                name = self._extract_text(name_node, source_bytes) if name_node else "Item"
                symbols.append(
                    ExtractedSymbol(
                        name=name,
                        type=SymbolType.CLASS,
                        file_path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        language="rust",
                    )
                )
                return

            elif node_type == "impl_item":
                type_node = node.child_by_field_name("type")
                impl_name = self._extract_text(type_node, source_bytes) if type_node else "Impl"
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        self._traverse_node(child, source_bytes, language_key, rel_path, symbols, in_class=impl_name)
                return

        # ==================== C / C++ ====================
        elif language_key == "cpp":
            if node_type == "preproc_include":
                symbols.append(
                    ExtractedSymbol(
                        name=self._extract_text(node, source_bytes),
                        type=SymbolType.IMPORT,
                        file_path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        language="cpp",
                    )
                )
                return

            elif node_type == "function_definition":
                declarator = node.child_by_field_name("declarator")
                name = self._extract_text(declarator, source_bytes) if declarator else "function"
                if "(" in name:
                    name = name.split("(")[0].strip()
                symbols.append(
                    ExtractedSymbol(
                        name=f"{in_class}::{name}" if in_class else name,
                        type=SymbolType.METHOD if in_class else SymbolType.FUNCTION,
                        file_path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        language="cpp",
                    )
                )
                return

            elif node_type in ("class_specifier", "struct_specifier"):
                name_node = node.child_by_field_name("name")
                name = self._extract_text(name_node, source_bytes) if name_node else "Class"
                symbols.append(
                    ExtractedSymbol(
                        name=name,
                        type=SymbolType.CLASS,
                        file_path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        language="cpp",
                    )
                )
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        self._traverse_node(child, source_bytes, language_key, rel_path, symbols, in_class=name)
                return

        # Default recursive walk for other node types
        for child in node.children:
            self._traverse_node(child, source_bytes, language_key, rel_path, symbols, in_class=in_class)


class RepositoryASTParser:
    """Parses source files across an entire repository into structured AST symbols."""

    def __init__(self, extractor: Optional[ASTSymbolExtractor] = None):
        self.extractor = extractor or ASTSymbolExtractor()

    def parse_file(self, full_path: str, repo_root: str) -> Optional[FileParseResult]:
        """Parse a single source file if supported."""
        ext = os.path.splitext(full_path)[1].lower()
        language_key = EXTENSION_TO_LANGUAGE.get(ext)
        if not language_key:
            return None

        rel_path = os.path.relpath(full_path, repo_root).replace("\\", "/")

        try:
            size = os.path.getsize(full_path)
            if size > MAX_PARSE_FILE_SIZE:
                return FileParseResult(
                    file_path=rel_path,
                    language=language_key,
                    warnings=[f"File skipped: exceeds maximum size limit ({size} bytes)"],
                )

            with open(full_path, "rb") as f:
                code_bytes = f.read()

            # Skip binary files containing null bytes
            if b"\0" in code_bytes[:1024]:
                return None

            return self.extractor.parse_source_code(code_bytes, language_key, rel_path)
        except Exception as e:
            return FileParseResult(
                file_path=rel_path,
                language=language_key,
                errors=[f"Failed to read/parse file: {str(e)}"],
            )

    def parse_repository(
        self,
        repo_path: str,
        max_files: int = 500,
    ) -> RepositoryParseResult:
        """Parse all supported code files in a repository directory."""
        repo_path = os.path.abspath(repo_path)
        file_results: List[FileParseResult] = []
        unsupported_files: List[str] = []
        errors: List[str] = []

        total_symbols = 0
        symbols_by_type: Dict[str, int] = {}
        symbols_by_lang: Dict[str, int] = {}

        if not os.path.exists(repo_path):
            errors.append(f"Repository directory does not exist: {repo_path}")
            return RepositoryParseResult(
                stats=ParseStats(),
                files=[],
                unsupported_files=[],
                errors=errors,
            )

        parsed_count = 0

        for root, dirs, files in os.walk(repo_path, followlinks=False):
            dirs[:] = [d for d in dirs if d not in IGNORED_PARSE_DIRS]

            for file_name in files:
                if parsed_count >= max_files:
                    break

                full_path = os.path.join(root, file_name)
                ext = os.path.splitext(file_name)[1].lower()
                rel_path = os.path.relpath(full_path, repo_path).replace("\\", "/")

                if ext in EXTENSION_TO_LANGUAGE:
                    lang = EXTENSION_TO_LANGUAGE[ext]
                    if self.extractor.grammar_manager.is_language_supported(lang):
                        result = self.parse_file(full_path, repo_path)
                        if result:
                            file_results.append(result)
                            parsed_count += 1
                            count = len(result.symbols)
                            total_symbols += count
                            symbols_by_lang[lang] = symbols_by_lang.get(lang, 0) + count
                            for sym in result.symbols:
                                t = sym.type.value
                                symbols_by_type[t] = symbols_by_type.get(t, 0) + 1
                    else:
                        unsupported_files.append(rel_path)
                else:
                    # Non-code or unsupported extension
                    pass

        stats = ParseStats(
            total_files_parsed=parsed_count,
            total_symbols_extracted=total_symbols,
            symbols_by_type=symbols_by_type,
            symbols_by_language=symbols_by_lang,
        )

        return RepositoryParseResult(
            stats=stats,
            files=file_results,
            unsupported_files=unsupported_files,
            errors=errors,
        )


def parse_repository_ast(repo_path: str, max_files: int = 500) -> RepositoryParseResult:
    """Convenience function to parse AST symbols from a repository directory."""
    parser = RepositoryASTParser()
    return parser.parse_repository(repo_path, max_files=max_files)

