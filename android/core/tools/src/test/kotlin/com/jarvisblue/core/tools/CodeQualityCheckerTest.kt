package com.jarvisblue.core.tools

import com.jarvisblue.core.model.FindingSeverity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CodeQualityCheckerTest {

    private val checker = CodeQualityChecker()

    @Test
    fun `detects unbalanced brackets`() {
        val report = checker.check("fun a() {\n  val x = 1\n")
        assertTrue(report.issues.any { it.message.contains("Unbalanced") })
    }

    @Test
    fun `flags non-null assertions`() {
        val report = checker.check("val name = user.name!!")
        assertTrue(report.issues.any { it.message.contains("!!") })
    }

    @Test
    fun `flags broad exception handlers`() {
        val report = checker.check("try { x() } catch (Exception e) { }")
        assertTrue(report.issues.any { it.message.contains("Broad exception") })
    }

    @Test
    fun `clean code reports nothing`() {
        val report = checker.check("fun add(a: Int, b: Int): Int = a + b")
        assertEquals(0, report.issues.size)
    }
}
