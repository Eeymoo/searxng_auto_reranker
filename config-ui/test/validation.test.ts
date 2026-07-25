import test from "node:test";
import assert from "node:assert/strict";
import {
  COEFFICIENT_MAX,
  COEFFICIENT_MIN,
  validateCoefficient,
  validateNonEmpty,
  validatePattern,
} from "../lib/validation.ts";

test("validateCoefficient: accepts value within range", () => {
  assert.equal(validateCoefficient(0), null);
  assert.equal(validateCoefficient(5.5), null);
  assert.equal(validateCoefficient(COEFFICIENT_MAX), null);
  assert.equal(validateCoefficient(COEFFICIENT_MIN), null);
});

test("validateCoefficient: rejects out-of-range", () => {
  assert.ok(validateCoefficient(15.0));
  assert.ok(validateCoefficient(-0.1));
  assert.ok(validateCoefficient(11));
});

test("validateCoefficient: rejects non-numbers", () => {
  assert.ok(validateCoefficient("3"));
  assert.ok(validateCoefficient(null));
  assert.ok(validateCoefficient(NaN));
});

test("validatePattern: accepts valid regex", () => {
  assert.equal(validatePattern(".*\\.gov\\.cn/.*"), null);
  assert.equal(validatePattern("^foo$"), null);
});

test("validatePattern: rejects empty or malformed regex", () => {
  assert.ok(validatePattern(""));
  assert.ok(validatePattern(null));
  assert.ok(validatePattern("(unclosed"));
});

test("validateNonEmpty: rejects empty / whitespace", () => {
  assert.ok(validateNonEmpty("name", ""));
  assert.ok(validateNonEmpty("name", "   "));
  assert.ok(validateNonEmpty("name", null));
  assert.equal(validateNonEmpty("name", "abc"), null);
});
