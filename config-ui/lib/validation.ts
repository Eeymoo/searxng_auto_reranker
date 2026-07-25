/** Shared validation helpers for rules / blacklist. */

export const COEFFICIENT_MIN = 0.0;
export const COEFFICIENT_MAX = 10.0;

export type ValidationError = { field: string; message: string };

/** Compile-coefficient range check (DB has a CHECK constraint as a backstop). */
export function validateCoefficient(value: unknown): ValidationError | null {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return { field: "coefficient", message: "coefficient must be a number" };
  }
  if (value < COEFFICIENT_MIN || value > COEFFICIENT_MAX) {
    return {
      field: "coefficient",
      message: `coefficient must be between ${COEFFICIENT_MIN} and ${COEFFICIENT_MAX}`,
    };
  }
  return null;
}

/** Validate a Python-flavoured regex by attempting to construct a RegExp. */
export function validatePattern(pattern: unknown): ValidationError | null {
  if (typeof pattern !== "string" || pattern.length === 0) {
    return { field: "pattern", message: "pattern must be a non-empty string" };
  }
  try {
    // JS RegExp is close enough to Python's syntax for validation purposes.
    new RegExp(pattern);
  } catch (e) {
    return { field: "pattern", message: "pattern is not valid regex" };
  }
  return null;
}

/** Validate that a string is non-empty (used for keyword / name fields). */
export function validateNonEmpty(
  field: string,
  value: unknown
): ValidationError | null {
  if (typeof value !== "string" || value.trim().length === 0) {
    return { field, message: `${field} must be a non-empty string` };
  }
  return null;
}
