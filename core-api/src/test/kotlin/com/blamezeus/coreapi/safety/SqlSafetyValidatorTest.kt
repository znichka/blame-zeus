package com.blamezeus.coreapi.safety

import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.junit.jupiter.params.ParameterizedTest
import org.junit.jupiter.params.provider.ValueSource

class SqlSafetyValidatorTest {

    private val validator = SqlSafetyValidator()

    @Test
    fun `plain SELECT is allowed`() {
        validator.validate("SELECT id FROM entities")
    }

    @Test
    fun `WITH RECURSIVE CTE is allowed`() {
        validator.validate("WITH RECURSIVE t AS (SELECT id FROM entities) SELECT * FROM t")
    }

    @Test
    fun `leading whitespace before SELECT is tolerated`() {
        validator.validate("   \n  SELECT id FROM entities")
    }

    @Test
    fun `lowercase select is allowed`() {
        validator.validate("select id from entities")
    }

    @ParameterizedTest
    @ValueSource(strings = ["DROP TABLE entities", "drop table entities", "  DROP TABLE entities"])
    fun `DROP is rejected`(sql: String) {
        assertThrows<IllegalArgumentException> { validator.validate(sql) }
    }

    @Test
    fun `DELETE is rejected`() {
        assertThrows<IllegalArgumentException> { validator.validate("DELETE FROM entities WHERE id = 1") }
    }

    @Test
    fun `INSERT is rejected`() {
        assertThrows<IllegalArgumentException> { validator.validate("INSERT INTO entities (name) VALUES ('x')") }
    }

    @Test
    fun `UPDATE is rejected`() {
        assertThrows<IllegalArgumentException> { validator.validate("UPDATE entities SET name = 'x'") }
    }

    @Test
    fun `embedded semicolon is rejected`() {
        assertThrows<IllegalArgumentException> { validator.validate("SELECT 1; DROP TABLE entities") }
    }

    @Test
    fun `trailing semicolon is rejected`() {
        assertThrows<IllegalArgumentException> { validator.validate("SELECT id FROM entities;") }
    }

    @Test
    fun `a column named updated_at is not mistaken for the UPDATE keyword`() {
        validator.validate("SELECT updated_at FROM entities")
    }

    @Test
    fun `a table named deleted_entities is not mistaken for the DELETE keyword`() {
        validator.validate("SELECT id FROM deleted_entities")
    }

    @Test
    fun `a statement not starting with SELECT or WITH is rejected`() {
        assertThrows<IllegalArgumentException> { validator.validate("EXPLAIN SELECT id FROM entities") }
    }

    @Test
    fun `blank input is rejected`() {
        assertThrows<IllegalArgumentException> { validator.validate("") }
    }
}
