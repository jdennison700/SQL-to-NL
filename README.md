# SQL to NL

Turns a SQL query into a plain-English sentence. The translation is
rule-based — the query is parsed into an AST with
[sqlglot](https://github.com/tobymao/sqlglot) and the tree is walked to build
the description. No LLM, no network calls.

```
SELECT Customers.CustomerName, Orders.OrderID
FROM Customers
LEFT JOIN Orders ON Customers.CustomerID = Orders.CustomerID;
```

> Get Customers.CustomerName, Orders.OrderID from Customers left join with
> Orders on Customers.CustomerID equals Orders.CustomerID

## Running the GUI

```sh
uv run main.py
```

A window opens with a box for your query and a **Describe** button
(Ctrl+Enter also works). The dialect dropdown selects the SQL dialect the
query is parsed as.

## Using it as a library

`describe` takes a parsed sqlglot expression, not a SQL string:

```python
import sqlglot
from lib.sql_parser import describe

describe(sqlglot.parse_one("SELECT * FROM users WHERE age > 30"))
# 'Get all columns from users where age is greater than 30'
```

## Supported SQL

`SELECT` queries only, covering column lists and aliases, `DISTINCT`,
aggregates (`COUNT`, `SUM`, `AVG`, `MIN`, `MAX`), joins, `WHERE` with
`AND`/`OR`/`=`/`<`/`>`/`IS`/`IS NOT`, `ORDER BY` and `LIMIT`.
