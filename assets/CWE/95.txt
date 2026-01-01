### Example 1.
def calculate_expression(user_expr):
    result = eval(user_expr)
    return result
### Example 2.

def execute_user_code(code_string):
    local_vars = dict()
    exec(code_string, dict(), local_vars)
    return local_vars
