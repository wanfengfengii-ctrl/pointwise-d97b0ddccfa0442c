from fractions import Fraction


class SingularMatrixError(ValueError):
    pass


def _matrix(values):
    rows = tuple(tuple(Fraction(value) for value in row) for row in values)
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError('expected a nonempty rectangular matrix')
    return rows


def _dot(left, right):
    return sum((a * b for a, b in zip(left, right, strict=True)), Fraction(0))


def multiply_matrices(left, right):
    left, right = _matrix(left), _matrix(right)
    if len(left[0]) != len(right):
        raise ValueError('matrix dimensions do not match')
    columns = tuple(zip(*right, strict=True))
    return tuple(tuple(_dot(row, column) for column in columns) for row in left)


def gram_matrix(matrix):
    columns = tuple(zip(*_matrix(matrix), strict=True))
    return tuple(tuple(_dot(left, right) for right in columns) for left in columns)


def solve_linear_system(matrix, right):
    matrix = _matrix(matrix)
    right = tuple(Fraction(value) for value in right)
    size = len(matrix)
    if size != len(matrix[0]) or len(right) != size:
        raise ValueError('expected a square system with one right-hand side')
    rows = [list(row) + [value] for row, value in zip(matrix, right, strict=True)]
    for column in range(size):
        pivot = next((index for index in range(column, size) if rows[index][column]), None)
        if pivot is None:
            raise SingularMatrixError('linear system is singular')
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        rows[column] = [value / divisor for value in rows[column]]
        for index, row in enumerate(rows):
            if index == column or not row[column]:
                continue
            factor = row[column]
            rows[index] = [
                value - factor * pivot_value
                for value, pivot_value in zip(row, rows[column], strict=True)
            ]
    return tuple(row[-1] for row in rows)
