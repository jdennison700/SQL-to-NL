import sqlglot
from sqlglot import exp

def describe(tree):
    select = tree
    cols = ", ".join(c.sql() for c in select.expressions)
    if cols == "*":
        cols = "all columns"

    table = select.find(exp.Table).sql()

    if select.args.get("distinct"):
        sentence = f"Get the distinct {cols} from {table}"
    else:
        sentence = f"Get {cols} from {table}"
    where = select.find(exp.Where)
    if where:
        sentence += f" where {describe_condition(where.this)}"

    order = select.find(exp.Order)
    if order:
        sentence += f" {describe_order(order)}"

    limit = select.find(exp.Limit)
    if limit:
        sentence += f" {describe_limit(limit)}"

    return sentence

def describe_condition(cond):

    if isinstance(cond, exp.And):
            left = describe_condition(cond.this)
            right = describe_condition(cond.expression)
            if isinstance(cond.this, exp.Or):
                left = f"({left})"
            if isinstance(cond.expression, exp.Or):
                right = f"({right})"
            return f"{left} and {right}"

    elif isinstance(cond, exp.Or):
        left = describe_condition(cond.this)
        right = describe_condition(cond.expression)
        if isinstance(cond.this, exp.And):
            left = f"({left})"
        if isinstance(cond.expression, exp.And):
            right = f"({right})"
        return f"{left} or {right}"

    elif isinstance(cond, exp.GT):
        return f"{cond.this.sql()} is greater than {cond.expression.sql()}"

    elif isinstance(cond, exp.EQ):
        return f"{cond.this.sql()} equals {cond.expression.sql()}"

    elif isinstance(cond, exp.LT):
        return f"{cond.this.sql()} is less than {cond.expression.sql()}"

    elif isinstance(cond, exp.Not) and isinstance(cond.this, exp.Is):
        inner = cond.this
        return f"{inner.this.sql()} is not {inner.expression.sql().lower()}"

    elif isinstance(cond, exp.Is):
        return f"{cond.this.sql()} is {cond.expression.sql().lower()}"

def describe_order(order):
    if isinstance(order, exp.Order):
        return f", in order by {', '.join(f'{e.this.sql()} {e.args.get('desc') and 'descending' or 'ascending'}' for e in order.expressions)}"

def describe_limit(limit):
    if isinstance(limit, exp.Limit):
        return f", limited to {limit.expression.sql()} results"




if __name__ == "__main__":
    tree = sqlglot.parse_one("SELECT TOP 3 id, name FROM table WHERE id IS NOT 1 ORDER BY age DESC", dialect="tsql")

    print(repr(tree))

    description = describe(tree)
    print(description)