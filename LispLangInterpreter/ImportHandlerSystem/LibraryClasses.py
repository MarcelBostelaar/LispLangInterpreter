from __future__ import annotations

import importlib
import os
from os.path import basename
from typing import List

from LispLangInterpreter.Config import langConfig
from LispLangInterpreter.Config.Singletons import MacroHandlerFrame, RuntimeHandlerFrame
from LispLangInterpreter.DataStructures.Classes import StackFrame, Value
from LispLangInterpreter.DataStructures.IErrorThrowable import IErrorThrowable
from LispLangInterpreter.Evaluator.EvaluatorCode import Eval
from LispLangInterpreter.Evaluator.MacroExpand import DemacroTop
from LispLangInterpreter.Evaluator.SupportFunctions import toAST
from LispLangInterpreter.ImportHandlerSystem.CompileStatus import CompileStatus
from LispLangInterpreter.Parser.ParserCode import parseAll
from LispLangInterpreter.Parser.ParserCombinator import SOF_value, EOF_value


class Searchable:
    def __init__(self, absPath):
        self.absPath = absPath
        self.name = None if absPath is None else basename(absPath).split(".")[0]
        self.parent = None
        self.compileStatus: CompileStatus = CompileStatus.Uncompiled
        self.values = {}

    def _findStart(self, callingStack: IErrorThrowable, pathElements: [str]) -> Searchable | None:
        raise NotImplementedError("Abstract")

    def _findInside(self, callingStack: IErrorThrowable, pathElements: [str]) -> Searchable | None:
        raise NotImplementedError("Abstract")

    def find(self, callingStack: IErrorThrowable, pathElements: [
        str]) -> Searchable | Value | None:
        # again to prevent constant back and forth search
        """
        Gets the specified searchable where the specified value is located, or None if not found
        :param callingStack: CallingStack to throw the error in
        :param pathElements: List of elements
        :return: Searchable or None
        """
        start = self._findStart(callingStack, pathElements)
        if start is None:
            return None
        return start._findInside(callingStack, pathElements[1:])

    def _getValue(self, callingStack: IErrorThrowable, name: str) -> Value | None:
        """
        Attempts to get a value from the given searchable
        :param name: Name of the item to import
        :return: Found value, or None if none was found.
        """
        raise NotImplementedError("Abstract")

    def execute(self, callingStack: IErrorThrowable):
        raise NotImplementedError("Abstract")


class Leaf(Searchable):
    def __init__(self, absPath, isLisp):
        super().__init__(absPath)
        self.isLisp = isLisp
        self.data = None

    def _findStart(self, callingStack: IErrorThrowable, pathElements: [str]) -> Searchable | None:
        if self.name == pathElements[0]:
            return self
        return self.parent._findStart(callingStack, pathElements)

    def _findInside(self, callingStack: IErrorThrowable, pathElements: [str]) -> Searchable | None:
        if len(pathElements) == 0:
            return self
        if pathElements[0] == self.name:
            if len(pathElements) == 2:
                return self._getValue(pathElements[1])
            return None  # Possible naming conflict, same file, but not looking for value in this file
        return None  # No match

    def _getValue(self, callingStack: IErrorThrowable, name: str) -> Value | None:
        if self.compileStatus != CompileStatus.Compiled:
            self.execute(callingStack)
        if self.isLisp:
            raise NotImplementedError()
        else:
            raise NotImplementedError()

    def execute(self, callingStack: IErrorThrowable):
        if self.compileStatus == CompileStatus.Compiled:
            raise Exception("Called execute on already compiled file, engine error")
        elif self.compileStatus == CompileStatus.Compiling:
            callingStack.throwError(
                "Tried to compile " + self.absPath + " while already compiling, circular dependency")
        else:
            self.compileStatus = CompileStatus.Compiling
            if self.isLisp:
                text = open(self.absPath, "r").read()
                parsed = parseAll.parse([SOF_value] + list(text) + [EOF_value])
                if len(parsed.remaining) != 0:
                    callingStack.throwError("Could not parse lisp file " + self.absPath)
                ast = toAST(parsed.content)
                demacroedCode = DemacroTop(StackFrame(ast, self).withHandlerFrame(MacroHandlerFrame))
                self.data = Eval(StackFrame(demacroedCode, self).withHandlerFrame(RuntimeHandlerFrame))
            else:
                importedModule = importlib.import_module(self.absPath)
                self.data = importedModule
            self.compileStatus = CompileStatus.Compiled


class Container(Searchable):
    def __init__(self, absPath, children: List[Searchable]):
        super().__init__(absPath)
        self.children = {x.name: x for x in children}
        self.fixChildren()

    def _findInside(self, callingStack: IErrorThrowable, pathElements: [str]) -> Searchable | None:
        if len(pathElements) == 0:
            return self
        if pathElements[0] in self.children.keys():
            return self.children[pathElements[0]]._findInside(callingStack, pathElements[1:])
        return None

    def fixChildren(self):
        for i in self.children.values():
            i.parent = self
        return self


class Folder(Container):
    def __init__(self, absPath, children):
        super().__init__(absPath, children)

    def _findStart(self, callingStack: IErrorThrowable, pathElements: [str]) -> Searchable | None:
        if self.name == pathElements[0]:
            return self
        return self.parent._findStart(callingStack, pathElements)


class Package(Container):
    def _getValue(self, callingStack: IErrorThrowable, name: str) -> Value | None:
        return self.children[self.packageFileName]._getValue(callingStack,name)

    def __init__(self, absPath, children, packageFileName):
        super().__init__(absPath, children)
        self.packageFileName = packageFileName

    def _findInside(self, callingStack: IErrorThrowable, pathElements: [str]) -> Searchable | None:
        if len(pathElements) > 1:
            # it's not looking for the package re-exports
            return super()._findInside(callingStack, pathElements)
        return self._getValue(callingStack, pathElements[0])

    def execute(self, callingStack: IErrorThrowable):
        self.children[self.packageFileName].execute(callingStack)


class LispPackage(Package):
    def __init__(self, absPath, children):
        super().__init__(absPath, children, langConfig.lispPackageFile)


class PythonPackage(Package):
    def __init__(self, absPath, children):
        super().__init__(absPath, children, "__init__")


class Library(Container):
    def __init__(self, absPath, children: List[Searchable]):
        super().__init__(absPath, children)

    def _findStart(self, callingStack: IErrorThrowable, pathElements: [str]) -> Searchable | None:
        return self._findInside(callingStack, pathElements)

    def _getValue(self, callingStack: IErrorThrowable, name: str) -> Value | None:
        raise Exception("Cannot get value from a general library folder")

    def execute(self, callingStack: IErrorThrowable):
        raise Exception("Cannot execute a general library folder")


class LibraryWithFallback(Library):
    def __init__(self, absPath, children: List[Searchable], fallback: Library | LibraryWithFallback):
        super().__init__(absPath, children)
        self.fallback = fallback

    def _findStart(self, callingStack: IErrorThrowable, pathElements: [str]) -> Searchable | None:
        return self._findInside(callingStack, pathElements)

    def _findInside(self, callingStack: IErrorThrowable, pathElements: [str]) -> Searchable | None:
        primary = super()._findInside(callingStack, pathElements)
        if primary is None:
            return self.fallback._findInside(callingStack, pathElements)
        return primary


def splitPathFully(path):
    splitted = []
    head = path
    tail = None
    while head is not "" and tail is not "":
        h, t = os.path.split(head)
        head = h
        tail = t
        if tail is not "":
            splitted.append(tail)
    if head is not "":
        splitted.append(head)
    splitted.reverse()
    return splitted
