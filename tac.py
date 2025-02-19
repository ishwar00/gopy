import abc
import syntree

from collections import defaultdict
from symbol_table import SymbolInfo
from typing import Any, Dict, List, Optional, Tuple
from tabulate import tabulate
from go_lexer import symtab  # type_table
from utils import print_error, print_line_marker_nowhitespace
from syntree import infer_expr_typename


class Quad:
    def __init__(self, dest, op1, op2, operator):
        self.dest = dest
        self.op1 = op1
        self.op2 = op2
        self.operator = operator
        self.scope_id = symtab.cur_scope

    def __str__(self):
        return f"{self.dest} = {self.op1} {self.operator} {self.op2}"

    def str_operation(self):
        return f"{self.op1} {self.operator} {self.op2}"


class Assign(Quad):
    """An assignment operation (to a single value)"""

    def __init__(self, dest, value, scope_id="1"):
        self.scope_id = scope_id
        super().__init__(dest, None, value, "=")

    def __str__(self):
        return f"{self.dest} = {self.op2}"


class Label(Quad):
    def __init__(self, name: str, index: int):
        self.name = name
        self.index = index

        super().__init__(name, None, None, "LABEL")

    def __str__(self):
        return f"LABEL {self.name}:"


class GoTo(Quad):
    def __init__(self, label_name: str):
        self.label_name = label_name

        super().__init__(label_name, None, None, "goto")

    def __str__(self):
        return f"goto {self.label_name}"


class Call(Quad):
    def __init__(self, label_name: str, res: Any):
        self.label_name = label_name
        self.res = res

        super().__init__(res, None, label_name, "call")

    def __str__(self):
        return f"{self.dest} = call {self.op2}"


class ConditionalGoTo(Quad):
    """if operation goto label_name1 else goto label_name2"""

    def __init__(
        self, label_name1: str, operation: "TempVar", label_name2: Optional[str] = None
    ):
        self.label_name1 = label_name1
        self.label_name2 = label_name2
        self.operation = operation

        super().__init__(label_name1, operation, label_name2, "if")

    def __str__(self):
        if self.label_name2 is None:
            return f"if {self.operation} goto {self.label_name1}"
        else:
            return (
                f"if {self.operation} goto {self.label_name1}"
                f" else goto {self.label_name2}"
            )


class Single(Quad):
    """Quad to store a single value like a keyword"""

    def __init__(self, value: Any):
        super().__init__(None, None, None, value)

    def __str__(self):
        return self.operator


class Double(Quad):
    """Quad to store two values"""

    def __init__(self, op, value, dest=None):
        super().__init__(dest, None, value, op)

    def __str__(self):
        if self.dest is None:
            return f"{self.operator} {self.op2}"
        else:
            return f"{self.dest} = {self.operator} {self.op2}"


class Operand(metaclass=abc.ABCMeta):
    @property
    @abc.abstractmethod
    def name(self):
        pass

    @abc.abstractmethod
    def is_const(self):
        pass

    @property
    @abc.abstractmethod
    def value(self):
        pass

    @value.setter
    @abc.abstractmethod
    def value(self, value: Any):
        pass

    def __str__(self):
        return self.name


class TempVar(Operand):
    def __init__(self, id: int, value: Any = None, type_: Any = None):
        self.__name = "t" + str(id)
        self.symbol = symtab.add_if_not_exists(self.name)
        self.symbol.const_flag = True if value is not None else False
        self.symbol.value = value
        self.symbol.type_ = type_

    @property
    def name(self):
        return self.__name

    @name.setter
    def name(self, id: int):
        self.__name = "t" + str(id)

    def is_const(self):
        return self.symbol.const_flag

    @property
    def value(self):
        if self.is_const():
            return self.symbol.value
        else:
            raise Exception(
                self.name + " is not a constant and has no value attribute!"
            )

    @value.setter
    def value(self, value: Any):
        self.symbol.const_flag = True
        self.symbol.value = value

    @property
    def type_(self):
        return self.symbol.type_

    @type_.setter
    def type_(self, value: Any):
        self.symbol.type_ = value

    def __repr__(self):
        return f"<Temp {self.name}>"

    def __hash__(self):
        return hash(self.symbol.name + self.symbol.scope_id)

    def __eq__(self, other):
        if isinstance(other, ActualVar):
            if (
                self.symbol.name == other.symbol.name
                and self.symbol.scope_id == self.symbol.scope_id
            ):
                return True
            return False
        return False


class ActualVar(Operand):
    def __init__(self, symbol: Optional[SymbolInfo]):
        self.__symbol = symbol
        self.symbol.const_flag = self.symbol.const

    @property
    def symbol(self):
        return self.__symbol

    @property
    def name(self):
        return self.symbol.name

    def is_const(self):
        return self.symbol.const_flag

    def deconstantize(self):
        self.symbol.const_flag = False

    @property
    def value(self):
        if self.is_const():
            return self.symbol.value
        else:
            raise Exception(
                self.name + " is not a constant and has no value attribute!"
            )

    @value.setter
    def value(self, value: Any):
        if self.symbol.const:
            raise Exception(
                self.name + " is a defined constant and its value cannot be changed!"
            )
        self.symbol.const_flag = True
        self.symbol.value = value

    @property
    def type_(self):
        return self.symbol.type_

    @type_.setter
    def type_(self, value: Any):
        self.symbol.type_ = value

    def __hash__(self):
        return hash(self.symbol.name + self.symbol.scope_id)

    def __eq__(self, other):
        if isinstance(other, ActualVar):
            if (
                self.symbol.name == other.symbol.name
                and self.symbol.scope_id == self.symbol.scope_id
            ):
                return True
            return False
        return False

    def __repr__(self):
        return f"<ActualVar {self.name}>"


class IntermediateCode:
    def __init__(self):
        self.code_list: List[Quad] = []
        self.temp_var_count = 0
        self.label_prefix_counts: Dict[str, int] = defaultdict(lambda: 0)
        self.label_map: Dict[str, Label] = {}
        self.loop_stack: List[Tuple[str, str]] = []

        # BUILT-IN functions (or labels)
        self._add_label(self.get_fn_label("fmt__Println"))
        self._add_label(self.get_fn_label("fmt__Printf"))
        self._add_label(self.get_fn_label("fmt__Print"))

    def get_new_temp_var(self, value: Any = None):
        self.temp_var_count += 1
        return TempVar(self.temp_var_count, value)

    def add_to_list(self, code: Quad):
        self.code_list.append(code)

    # generating labels
    @staticmethod
    def get_fn_label(fn_name: str):
        return f"FUNCTION_{fn_name}"

    @staticmethod
    def get_fn_end_label(fn_name: str):
        return f"FUNCTION_END_{fn_name}"

    def _add_label(self, label_name: str, label_index: int = -1) -> Label:
        """Private function for adding label without adding
        to the code_list"""
        label = Label(label_name, label_index)
        self.label_map[label_name] = label

        return label

    def add_label(self, label_name: str) -> Label:
        """Add given label name. For named labels like functions, etc."""
        if label_name in self.label_map:
            raise Exception(f"Label {label_name} already exists")

        label = self._add_label(label_name, len(self.code_list))

        self.code_list.append(label)

        return label

    def get_new_increment_label(self, prefix="label") -> str:
        """Return a new label with an incremental number name.
        Ex: label_1, label_2, etc.

        Must be added using self.add_label later!
        """
        self.label_prefix_counts[prefix] += 1
        name = f"{prefix}_{self.label_prefix_counts[prefix]}"

        return name

    def get_label(self, label_name: str) -> Label:
        return self.label_map[label_name]

    def add_goto(self, label_name: str) -> GoTo:
        if label_name not in self.label_map:
            raise Exception(f"Label {label_name} does not exist, cannot goto to it")
        goto_stmt = GoTo(label_name)
        self.add_to_list(goto_stmt)

        return goto_stmt

    def add_call(self, label_name: str, res) -> Call:
        if label_name not in self.label_map:
            raise Exception(f"Label {label_name} does not exist, cannot goto to it")
        call_stmt = Call(label_name, res)
        self.add_to_list(call_stmt)

        return call_stmt

    def enter_new_loop(self, start_label: str, end_label: str):
        self.loop_stack.append((start_label, end_label))

    def exit_loop(self):
        self.loop_stack.pop()

    def is_inloop(self):
        return len(self.loop_stack) > 0

    def get_nearest_loop(self):
        return self.loop_stack[-1]

    def print_three_address_code(self):
        for i in self.code_list:
            print(i)

    def __str__(self) -> str:
        return str(
            tabulate(
                [
                    [i.dest, i.op1, i.operator, i.op2]
                    for i in self.code_list
                ],
                headers=["Dest", "Operand 1", "Operator", "Operand 2"],
                tablefmt="psql",
            )
        )


def tac_Assignment(
    ic: IntermediateCode,
    node: syntree.Assignment,
    new_children: List[List[Any]],
    return_val: List[Any],
):
    left = new_children[0][0]
    right = new_children[1][0]
    if len(node.operator) == 2 and node.operator[1] == "=":
        ic.add_to_list(Quad(left, left, right, node.operator[0]))
        return_val.append(left)
    elif node.operator == "=":
        ic.add_to_list(Assign(left, right))
        return_val.append(left)

    return_val.append(node)


def tac_BinOp(
    ic: IntermediateCode,
    node: syntree.BinOp,
    new_children: List[List[Any]],
    return_val: List[Any],
):
    temp = ic.get_new_temp_var()
    temp.type_ = node.type_

    # the children can be temporaries made in the _recur_codegen call above
    # so they are stored in new_children which is used here
    # each return value is a list, so the second [0] is needed
    ic.add_to_list(Quad(temp, new_children[0][0], new_children[1][0], node.operator))

    return_val.append(temp)


def tac_UnaryOp(
    ic: IntermediateCode,
    node: syntree.UnaryOp,
    new_children: List[List[Any]],
    return_val: List[Any],
):
    if node.operator == "++" or node.operator == "--":

        ic.add_to_list(
            Quad(new_children[0][0], new_children[0][0], 1, node.operator[0])
        )

        return_val.append(new_children[0][0])

    else:
        temp = ic.get_new_temp_var()
        temp.type_ = node.type_

        ic.add_to_list(Double(node.operator, new_children[0][0], temp))

        return_val.append(temp)


def tac_Literal(
    ic: IntermediateCode,
    node: syntree.Literal,
    new_children: List[List[Any]],
    return_val: List[Any],
):
    # temp = ic.get_new_temp_var(node.value)

    # TODO: how to handle type here?
    # ic.add_to_list(Assign(temp, node.value))
    # ic.add_to_list(node.value)

    if not isinstance(node.value, syntree.Node):
        return_val.append(node)
    else:
        if len(new_children) > 1:
            if isinstance(new_children[0][0], syntree.Array):
                arr = "{" + ", ".join(map(lambda x: str(x[0]), new_children[1])) + "}"
                return_val.append(arr)
            else:
                return_val.append(new_children[1][0])
        else:
            return_val.append(new_children[0][0])


def tac_Keyword(
    ic: IntermediateCode,
    node: syntree.Keyword,
    new_children: List[List[Any]],
    return_val: List[Any],
):
    if node.kw == "RETURN":
        if len(new_children) > 0 and len(new_children[0]) > 0:
            ic.add_to_list(Double("return", new_children[0][0]))
        else:
            ic.add_to_list(Single("return"))
    elif node.kw == "BREAK" or node.kw == "CONTINUE":
        if not ic.is_inloop():
            print_error("Invalid keyword usage")
            print(f"Keyword {node.kw} not allowed outside a loop")
            print_line_marker_nowhitespace(node.lineno)
    else:
        print(f"Keyword {node.kw} not implemented yet!")

    return_val.append(node)


def tac_PrimaryExpr(
    ic: IntermediateCode,
    node: syntree.PrimaryExpr,
    new_children: List[List[Any]],
    return_val: List[Any],
):
    if isinstance(node.data, tuple) and node.data[0] == "identifier":
        # a simple identifier
        if not node.children:
            if node.ident is None:
                print(f"Skipping undeclared identifier {node.data[1]}")
            else:
                return_val.append(ActualVar(node.ident))

        # not so simple identifier
        elif len(node.children) == 1 and isinstance(node.children[0], syntree.Index):
            arr_name = node.data[1]
            index: syntree.Index = node.children[0]
            ident: Optional[SymbolInfo] = node.ident

            base_addr_t = ic.get_new_temp_var()
            base_addr_t.type_ = "int"
            ic.add_to_list(Assign(base_addr_t, f"base({arr_name})"))
            # return_val.append(base_addr_t)

            if ident is not None:
                ind = new_children[0][0][0]
                # width = syntree.Literal(
                #     "int", type_table.get_type(ident.type_.eltype).storage
                # )
                width = syntree.Literal(
                    "int", ident.type_.storage, None
                )

                offset_t = ic.get_new_temp_var()
                offset_t.type_ = "int"
                ic.add_to_list(Quad(offset_t, ind, width, "*"))

                index_t = ic.get_new_temp_var()
                index_t.type_ = "int"
                ic.add_to_list(Quad(index_t, base_addr_t, offset_t, "+"))

                res_t = ic.get_new_temp_var()
                res_t.type_ = ident.type_.eltype
                ic.add_to_list(Quad(res_t, arr_name, index_t, "[]"))

                return_val.append(res_t)
            else:
                print("uhhh could not get type")

                return_val.append(node)

        else:

            return_val.append(node)

    elif (
        node.data is None
        and len(new_children) == 2
        and isinstance(new_children[1][0], syntree.Index)
    ):
        # TODO: do array/slice indexing here
        arr_name_, index_ = new_children
        arr_name = arr_name_[0]
        index: syntree.Index = index_[0]
        ident: Optional[SymbolInfo] = node.ident

        # temp1 = ic.get_new_temp_var()
        base_addr_t = ic.get_new_temp_var()
        base_addr_t.type_ = "int"
        ic.add_to_list(Assign(base_addr_t, f"base({arr_name})"))
        return_val.append(base_addr_t)

        if ident is not None:
            print(ident.type_)
        else:
            print("This should not be None, something is wrong", index, arr_name)

    # TODO: implement other variants of PrimaryExpr

    else:
        return_val.append(node)


def tac_Index(
    ic: IntermediateCode,
    node: syntree.Index,
    new_children: List[List[Any]],
    return_val: List[Any],
):
    return_val.append(new_children[0])


def tac_pre_VarDecl(ic: IntermediateCode, node: syntree.VarDecl):
    if len(node.children) > 1 and isinstance(node.children[1], syntree.BinOp):
        op = node.children[1]

        if isinstance(op.left, syntree.Literal):
            if isinstance(op.right, syntree.Literal):
                ic.add_to_list(
                    Quad(ActualVar(node.symbol), op.left, op.right, op.operator)
                )
                node.children.remove(op)
            elif isinstance(op.children[1], syntree.PrimaryExpr):
                right = _recur_codegen(op.children[1], ic)[0]
                ic.add_to_list(
                    Quad(ActualVar(node.symbol), op.left, right, op.operator)
                )
                node.children.remove(op)

        elif isinstance(op.children[0], syntree.PrimaryExpr):
            left = _recur_codegen(op.children[0], ic)[0]

            if isinstance(op.right, syntree.Literal):
                ic.add_to_list(
                    Quad(ActualVar(node.symbol), left, op.right, op.operator)
                )
                node.children.remove(op)

            elif isinstance(op.children[1], syntree.PrimaryExpr):
                right = _recur_codegen(op.children[1], ic)[0]
                ic.add_to_list(Quad(ActualVar(node.symbol), left, right, op.operator))
                node.children.remove(op)


def tac_VarDecl(
    ic: IntermediateCode,
    node: syntree.VarDecl,
    new_children: List[List[Any]],
    return_val: List[Any],
):
    if len(new_children) > 1:
        if len(new_children[1]) > 0:
            ic.add_to_list(Assign(ActualVar(node.symbol), new_children[1][0]))
        return_val.append(node.ident.ident_name)


def tac_List(
    ic: IntermediateCode,
    node: syntree.List,
    new_children: List[List[Any]],
    return_val: List[Any],
):
    return_val.extend(new_children)


def tac_pre_Function(ic: IntermediateCode, node: syntree.Function):
    symtab.enter_scope()
    symtab.enter_scope()

    fn_name = syntree.FunctionCall.get_fn_name(node.fn_name)
    fn_label = ic.get_fn_label(fn_name)
    ic.add_label(fn_label)


def tac_Function(
    ic: IntermediateCode,
    node: syntree.Function,
    new_children: List[List[Any]],
    return_val: List[Any],
):
    fn_name = syntree.FunctionCall.get_fn_name(node.fn_name)
    fn_label = ic.get_fn_end_label(fn_name)
    ic.add_label(fn_label)

    symtab.leave_scope()
    symtab.leave_scope()


def tac_Arguments(
    ic: IntermediateCode,
    node: syntree.Arguments,
    new_children: List[List[Any]],
    return_val: List[Any],
):
    for child in new_children:
        if isinstance(child, list):
            for subchild in child:
                if isinstance(subchild, list):
                    for subsubchild in subchild:
                        ic.add_to_list(Double("push", subsubchild))
                        return_val.append(subsubchild)
                else:
                    ic.add_to_list(Double("push", subchild))
                    return_val.append(subchild)
        else:
            ic.add_to_list(Double("push", child[0]))
            return_val.append(child[0])


def tac_FunctionCall(
    ic: IntermediateCode,
    node: syntree.FunctionCall,
    new_children: List[List[Any]],
    return_val: List[Any],
):
    label = ic.get_fn_label(node.get_fn_name(node.fn_name))
    temp = ic.get_new_temp_var()
    temp.type_ = node.type_
    ic.add_call(label, temp)
    return_val.append(temp)


def tac_pre_IfStmt(
    ic: IntermediateCode,
    node: syntree.IfStmt,
):
    symtab.enter_scope()

    # there can be a statement to be executed just before
    # the condition. specified as "if a := 10; a > 5 {...}"
    # we process the statement before anything else and remove
    # it from the children
    before_statement = node.statement
    if before_statement is not None:
        _recur_codegen(before_statement, ic)
        node.children.remove(before_statement)

    # we'll process the condition here
    # so we are removing it from the children
    condition = node.expr
    node.children.remove(condition)

    condition_res = _recur_codegen(condition, ic)[0]

    symtab.enter_scope()

    # now add the actual if statement
    true_label = ic.get_new_increment_label("if_true")
    false_label = ic.get_new_increment_label("if_false")
    g1 = ConditionalGoTo(true_label, condition_res, false_label)
    ic.add_to_list(g1)
    ic.add_label(true_label)

    # now the body (after true label)
    body = node.body
    node.children.remove(body)
    _recur_codegen(body, ic)
    # false label after body
    ic.add_label(false_label)

    symtab.leave_scope()

    # else part
    next_ = node.next_
    if next_ is not None:
        symtab.enter_scope()

        node.children.remove(next_)
        _recur_codegen(next_, ic)

        symtab.leave_scope()

    symtab.leave_scope()


def tac_IfStmt(
    ic: IntermediateCode,
    node: syntree.IfStmt,
    new_children: List[List[Any]],
    return_val: List[Any],
):
    pass


def tac_pre_ForStmt(ic: IntermediateCode, node: syntree.ForStmt):
    symtab.enter_scope()

    clause_typename = infer_expr_typename(node.clause)
    if clause_typename == "bool":
        # start of loop
        start_label = ic.get_new_increment_label("for_simple_start")
        ic.add_label(start_label)

        # the condition
        condition = node.clause
        node.children.remove(condition)

        condition_res = _recur_codegen(condition, ic)[0]

        true_label = ic.get_new_increment_label("for_simple_true")
        end_label = ic.get_new_increment_label("for_simple_end")

        symtab.enter_scope()

        # actual if else
        g1 = ConditionalGoTo(true_label, condition_res, end_label)
        ic.add_to_list(g1)
        ic.add_label(true_label)

        ic.enter_new_loop(start_label, end_label)

        # now the body (after true label)
        body = node.body
        if body is not None:
            node.children.remove(body)
            _recur_codegen(body, ic)
        # loop back to start label
        ic.add_goto(start_label)
        # end label after body
        ic.add_label(end_label)

        ic.exit_loop()

    elif isinstance(node.clause, syntree.ForClause):
        clause = node.clause

        # init statement (first part of for)
        if clause.init is not None:
            _recur_codegen(clause.init, ic)
            clause.children.remove(clause.init)

        # start of loop (just before condition)
        start_label = ic.get_new_increment_label("for_cmpd_start")
        ic.add_label(start_label)

        # the condition
        condition = clause.cond
        clause.children.remove(condition)
        condition_res = _recur_codegen(condition, ic)[0]

        true_label = ic.get_new_increment_label("for_cmpd_true")
        end_label = ic.get_new_increment_label("for_cmpd_end")

        symtab.enter_scope()

        # actual if else
        g1 = ConditionalGoTo(true_label, condition_res, end_label)
        ic.add_to_list(g1)
        ic.add_label(true_label)

        ic.enter_new_loop(start_label, end_label)

        # now the body (after true label)
        body = node.body
        if body is not None:
            node.children.remove(body)
            _recur_codegen(body, ic)
        # the post statement (increment/decrement)
        if clause.post is not None:
            _recur_codegen(clause.post, ic)
            clause.children.remove(clause.post)
        # loop back to start label
        ic.add_goto(start_label)
        # end label after body
        ic.add_label(end_label)

        ic.exit_loop()

    else:
        print("Could not determine clause type")

    symtab.leave_scope()


def tac_ForStmt(
    ic: IntermediateCode,
    node: syntree.ForStmt,
    new_children: List[List[Any]],
    return_val: List[Any],
):
    symtab.leave_scope()


ignored_nodes = {"Identifier", "Type", "Array"}


def _recur_codegen(node: syntree.Node, ic: IntermediateCode):
    # process all child nodes before parent
    # ast is from right to left, so need to traverse in reverse order

    node_class_name = node.__class__.__name__

    # call TAC functions before processing children
    # these have the prefix tac_pre_
    tac_pre_fn_name = f"tac_pre_{node_class_name}"
    if tac_pre_fn_name in globals():
        globals()[tac_pre_fn_name](ic, node)

    # recurse over children
    new_children = []
    for child in reversed(node.children):
        new_children.append(_recur_codegen(child, ic))
    new_children.reverse()

    return_val = []

    # call appropriate TAC functions after processing children
    # at this point, the children are already in the IC
    tac_fn_name = f"tac_{node_class_name}"
    if tac_fn_name in globals():
        globals()[tac_fn_name](ic, node, new_children, return_val)

    elif node_class_name in ignored_nodes:
        return_val.append(node)

    else:

        return_val.append(node)

    return return_val


def intermediate_codegen(ast: syntree.Node) -> IntermediateCode:
    ic = IntermediateCode()

    _recur_codegen(ast, ic)

    return ic
