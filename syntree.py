from typing import Optional

from go_lexer import symtab


class Node:
    """Node of an AST

    Warning: pls don't change the children values after setting them
    for nodes which depend on it"""

    def __init__(self, name, **kwargs):
        self.name = name
        self.children: list = [c for c in kwargs["children"] if c is not None]
        self.data = kwargs.get("data", None)

    def __repr__(self):
        return str(self)

    def __str__(self):
        if self.data is not None:
            return f"<{self.name}: {str(self.data)}>"
        else:
            return f"<{self.name}>"

    def data_str(self) -> str:
        return "" if self.data is None else str(self.data)

    def add_child(self, child):
        if child is not None:
            self.children.append(child)


class BinOp(Node):
    """Node for binary operations"""

    def __init__(self, operator, left=None, right=None):
        super().__init__("Binary", children=[left, right], data=operator)
        self.operator = self.data
        self.left = left
        self.right = right


class Assignment(BinOp):
    """Node for assignment operations"""


class UnaryOp(Node):
    """Node for unary operations"""

    def __init__(self, operator, operand):
        if isinstance(operand, UnaryOp) and operand.operator is None:
            operand = operand.operand
        super().__init__("Unary", children=[operand], data=operator)
        self.operand = operand
        self.operator = operator


class PrimaryExpr(Node):
    """Node for PrimaryExpr

    Ref: https://golang.org/ref/spec#PrimaryExpr
    """

    def __init__(self, operand, children=None):
        super().__init__(
            "PrimaryExpr", children=[] if children is None else children, data=operand
        )

    def data_str(self):
        # self.data can be an IDENTIFIER sometimes, so just show the name
        if isinstance(self.data, tuple) and self.data[0] == "identifier":
            return f"identifier: {self.data[1]}"
        else:
            return super().data_str()


class Literal(Node):
    """Node to store literals"""

    def __init__(self, type_, value):
        super().__init__(f"{type_} literal", children=[], data=(type_, value))
        self.type_ = type_
        self.value = value

    def data_str(self):
        return f"type: {self.type_}, value: {self.value}"


class Import(Node):
    """Node to store imports"""

    def __init__(self, pkg_name, import_path):
        # import_path is a STRING_LIT, so it has ("string", value)
        super().__init__("import", children=[], data=(pkg_name, import_path))

    def data_str(self):
        return f"name: {self.data[0]}, path: {self.data[1][1]}"


class List(Node):
    """Node to store literals"""

    def __init__(self, children):
        super().__init__("LIST", children=children)
        self.append = self.add_child

    def __iter__(self):
        return iter(self.children)

    def __len__(self):
        return len(self.children)


class Arguments(Node):
    """Node to store function arguments"""

    def __init__(self, expression_list):
        super().__init__("arguments", children=[expression_list])
        self.expression_list = expression_list


class Signature(Node):
    """Node to store function signature"""

    def __init__(self, parameters, result=None):
        super().__init__("signature", children=[parameters, result])
        self.parameters = parameters
        self.result = result


class Function(Node):
    """Node to store function declaration"""

    def __init__(self, name, signature, lineno: int, body=None):
        super().__init__("FUNCTION", children=[signature, body], data=(name, lineno))
        self.data: tuple
        if name is not None:
            symtab.declare_new_variable(
                name[1], lineno, 0, type_="FUNCTION", const=True, value=self
            )

        self.fn_name = name
        self.lineno = lineno
        self.signature = signature
        self.body = body

    def data_str(self):
        return f"name: {self.fn_name}, lineno: {self.lineno}"


class Type(Node):
    """Parent class for all types"""


class Array(Type):
    """Node for an array type"""

    def __init__(self, eltype, length):
        super().__init__("ARRAY", children=[length], data=eltype)
        self.eltype = eltype
        self.length = length

    def data_str(self):
        return f"eltype: {self.eltype}"


class Identifier(Node):
    """Node for identifiers"""

    def __init__(self, ident_tuple, lineno):
        super().__init__(
            "IDENTIFIER", children=[], data=(ident_tuple[1], lineno, ident_tuple[2])
        )
        # symtab.add_if_not_exists(ident_tuple[1])
        self.ident_name = ident_tuple[1]
        self.lineno = lineno
        self.col_num = ident_tuple[2]

    def add_symtab(self):
        symtab.add_if_not_exists(self.ident_name)

    def data_str(self):
        return (
            f"name: {self.ident_name}, lineno: {self.lineno}"
        )


class QualifiedIdent(Node):
    """Node for qualified identifiers"""

    def __init__(self, package_name, identifier):
        super().__init__("IDENTIFIER", children=[], data=(package_name, identifier))

    def data_str(self):
        return f"package: {self.data[0][1]}, name: {self.data[1][1]}"


class VariableDecl(Node):
    """Node to store variable and constant declarations"""

    def __init__(
        self,
        identifier_list: List,
        type_=None,
        expression_list: Optional[List] = None,
        const: bool = False,
    ):
        super().__init__(
            "DECL",
            children=[identifier_list, expression_list],
            data=(type_, const),
        )

        if expression_list is None:
            # TODO: implement default values
            ident: Identifier
            for ident in identifier_list:
                symtab.declare_new_variable(
                    ident.ident_name,
                    ident.lineno,
                    ident.col_num,
                    type_=type_,
                    const=const,
                )
        elif len(identifier_list) == len(expression_list):
            ident: Identifier
            expr: Node
            for ident, expr in zip(identifier_list, expression_list):
                # TODO: check value is appropriate for type
                symtab.declare_new_variable(
                    ident.ident_name,
                    ident.lineno,
                    ident.col_num,
                    type_=type_,
                    value=expr,
                    const=const,
                )
        else:
            raise NotImplementedError("Declaration with unpacking not implemented yet")

        self.expression_list = expression_list
        self.identifier_list = identifier_list
        self.type_ = type_
        self.is_const = const

    def data_str(self):
        return f"type: {self.type_}, is_const: {self.is_const}"


class ParameterDecl(Node):
    def __init__(self, type_, vararg=False, ident_list=None):
        super().__init__("PARAMETERS", children=[type_, ident_list], data=vararg)
        self.type_ = type_
        self.vararg = vararg
        self.ident_list = ident_list
        if ident_list is not None:
            self.var_decl = VariableDecl(ident_list)

    def data_str(self):
        return f"is_vararg: {self.vararg}"


class IfStmt(Node):
    def __init__(self, body, expr, statement=None, next_=None):
        super().__init__("IF", children=[statement, expr, body, next_])
        self.statement = statement
        self.expr = expr
        self.body = body
        self.next_ = next_


class ForStmt(Node):
    def __init__(self, body, clause=None):
        super().__init__("FOR", children=[body, clause])
        self.body = body
        self.clause = clause


class ForClause(Node):
    def __init__(self, init, cond, post):
        super().__init__("FOR_CLAUSE", children=[init, cond, post])
        self.init = init
        self.cond = cond
        self.post = post


class RangeClause(Node):
    def __init__(self, expr, ident_list=None, expr_list=None):
        if ident_list is not None:
            self.var_decl = VariableDecl(ident_list, expr)
        else:
            self.var_decl = None
        super().__init__("RANGE", children=[expr, ident_list, expr_list, self.var_decl])
        self.expr = expr
        self.ident_list = ident_list
        self.expr_list = expr_list


class Struct(Node):
    def __init__(self, field_decl_list):
        self.fields = []

        for i in field_decl_list:
            i: StructFieldDecl
            if i.ident_list is not None:
                for ident in i.ident_list:
                    ident: Identifier
                    self.fields.append(StructField(ident.ident_name, i.type_, i.tag))
            elif i.embed_field is not None:
                # TODO: handle pointer type here
                self.fields.append(StructField(i.embed_field[1], None, i.tag))

        super().__init__("Struct", children=self.fields)


class StructField(Node):
    def __init__(self, name, type_, tag):
        self.f_name = name
        self.type_ = type_
        self.tag = tag

        super().__init__("StructField", children=[], data=(name, type_, tag))

    def data_str(self):
        return f"name: {self.f_name}, type: {self.type_}, tag: {self.tag}"


class StructFieldDecl:
    def __init__(self, ident_list_or_embed_field, type_=None, tag=None):
        if isinstance(ident_list_or_embed_field, List):
            self.ident_list = ident_list_or_embed_field
            self.embed_field = None
        else:
            self.embed_field = ident_list_or_embed_field
            self.ident_list = None

        self.type_ = type_
        self.tag = tag
