"""Unit tests for the Tree-sitter AST parser engine."""

import os
import pytest

from app.parser import (
    ASTSymbolExtractor,
    RepositoryASTParser,
    parse_repository_ast,
)
from app.schemas import SymbolType


@pytest.fixture
def extractor():
    return ASTSymbolExtractor()


def test_python_ast_parsing(extractor):
    """Verify function, class, method, parameters, and imports in Python."""
    code = b"""
import os
from sys import path

class DataProcessor:
    def process_item(self, item_id: int, flag: bool = True):
        return item_id

def standalone_task(data: list) -> int:
    return len(data)
"""
    result = extractor.parse_source_code(code, "python", "service.py")

    assert len(result.errors) == 0
    symbols = result.symbols

    names = {s.name: s for s in symbols}

    # Imports
    assert any(s.type == SymbolType.IMPORT and "import os" in s.name for s in symbols)
    assert any(s.type == SymbolType.IMPORT and "from sys import path" in s.name for s in symbols)

    # Class
    assert "DataProcessor" in names
    assert names["DataProcessor"].type == SymbolType.CLASS

    # Method
    assert "DataProcessor.process_item" in names
    method = names["DataProcessor.process_item"]
    assert method.type == SymbolType.METHOD
    assert "item_id: int" in method.parameters
    assert method.start_line == 6

    # Function
    assert "standalone_task" in names
    func = names["standalone_task"]
    assert func.type == SymbolType.FUNCTION
    assert "data: list" in func.parameters


def test_javascript_ast_parsing(extractor):
    """Verify functions, arrow functions, classes, imports, and exports in JS."""
    code = b"""
import React from 'react';

export class AuthManager {
    login(username, password) {
        return true;
    }
}

export function validateInput(text) {
    return text.length > 0;
}

export const helper = (x, y) => x + y;
"""
    result = extractor.parse_source_code(code, "javascript", "auth.js")

    assert len(result.errors) == 0
    symbols = result.symbols
    names = {s.name: s for s in symbols}

    assert any(s.type == SymbolType.IMPORT for s in symbols)
    assert any(s.type == SymbolType.EXPORT for s in symbols)
    assert "AuthManager" in names
    assert names["AuthManager"].type == SymbolType.CLASS

    assert "AuthManager.login" in names
    assert names["AuthManager.login"].type == SymbolType.METHOD

    assert "validateInput" in names
    assert names["validateInput"].type == SymbolType.FUNCTION

    assert "helper" in names
    assert names["helper"].type == SymbolType.FUNCTION


def test_typescript_ast_parsing(extractor):
    """Verify TypeScript / TSX constructs."""
    code = b"""
import { FC } from 'react';

export class AppService {
    fetchData(): Promise<void> {}
}

export const MyComponent: FC = () => {
    return null;
};
"""
    result = extractor.parse_source_code(code, "typescript", "app.ts")
    assert len(result.errors) == 0

    names = {s.name: s for s in result.symbols}
    assert "AppService" in names
    assert names["AppService"].type == SymbolType.CLASS
    assert "AppService.fetchData" in names


def test_java_ast_parsing(extractor):
    """Verify Java class, interface, method, and import extraction."""
    code = b"""
package com.synapse;
import java.util.List;

public class UserService {
    public void createUser(String name, int age) {
    }
}
"""
    result = extractor.parse_source_code(code, "java", "UserService.java")
    assert len(result.errors) == 0

    names = {s.name: s for s in result.symbols}
    assert any(s.type == SymbolType.IMPORT and "java.util.List" in s.name for s in result.symbols)
    assert "UserService" in names
    assert "UserService.createUser" in names
    assert names["UserService.createUser"].type == SymbolType.METHOD


def test_go_ast_parsing(extractor):
    """Verify Go function, method with receiver, and type struct extraction."""
    code = b"""
package main
import "fmt"

type Worker struct {
    id int
}

func (w *Worker) Execute(task string) error {
    return nil
}

func Run() {
    fmt.Println("Running")
}
"""
    result = extractor.parse_source_code(code, "go", "main.go")
    assert len(result.errors) == 0

    names = {s.name: s for s in result.symbols}
    assert any(s.type == SymbolType.IMPORT and "fmt" in s.name for s in result.symbols)
    assert "Worker" in names
    assert names["Worker"].type == SymbolType.CLASS
    assert "Run" in names
    assert names["Run"].type == SymbolType.FUNCTION


def test_rust_ast_parsing(extractor):
    """Verify Rust struct, impl methods, functions, and use declarations."""
    code = b"""
use std::collections::HashMap;

pub struct Engine {
    power: u32,
}

impl Engine {
    pub fn new(power: u32) -> Self {
        Engine { power }
    }
}

fn start() {}
"""
    result = extractor.parse_source_code(code, "rust", "main.rs")
    assert len(result.errors) == 0

    names = {s.name: s for s in result.symbols}
    assert any(s.type == SymbolType.IMPORT for s in result.symbols)
    assert "Engine" in names
    assert "Engine.new" in names
    assert "start" in names


def test_cpp_ast_parsing(extractor):
    """Verify C++ classes, methods, and includes."""
    code = b"""
#include <iostream>

class Vector3 {
public:
    float magnitude() {
        return 0.0f;
    }
};

int calculate() {
    return 42;
}
"""
    result = extractor.parse_source_code(code, "cpp", "vector.cpp")
    assert len(result.errors) == 0

    names = {s.name: s for s in result.symbols}
    assert any(s.type == SymbolType.IMPORT for s in result.symbols)
    assert "Vector3" in names
    assert "Vector3::magnitude" in names
    assert "calculate" in names


def test_syntax_error_resilience(extractor):
    """Verify parser extracts partial symbols and warns on broken syntax without throwing."""
    broken_code = b"""
def valid_func(x):
    return x

def broken_syntax(
    # missing closing paren and body
"""
    result = extractor.parse_source_code(broken_code, "python", "broken.py")
    assert len(result.errors) == 0
    assert len(result.warnings) > 0  # Should flag syntax error
    assert any(s.name == "valid_func" for s in result.symbols)


def test_repository_ast_parsing(temp_repo):
    """Verify repository-level AST traversal and aggregated metrics."""
    res = parse_repository_ast(temp_repo)
    assert res.stats.total_files_parsed >= 2  # main.py and index.js
    assert res.stats.total_symbols_extracted > 0
    assert "python" in res.stats.symbols_by_language
    assert "javascript" in res.stats.symbols_by_language

