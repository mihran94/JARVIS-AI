package com.jarvisblue.core.common

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RedactorTest {

    @Test
    fun `redacts openai style keys`() {
        val out = Redactor.redact("using sk-abcdefghijklmnopqrstuvwx now")
        assertFalse(out.contains("sk-abcdefghijklmnopqrstuvwx"))
        assertTrue(out.contains("REDACTED"))
    }

    @Test
    fun `redacts assignment style secrets but keeps the key name`() {
        val out = Redactor.redact("api_key=superSecretValue123")
        assertFalse(out.contains("superSecretValue123"))
        assertTrue(out.contains("api_key"))
        assertTrue(out.contains("REDACTED"))
    }

    @Test
    fun `redacts bearer authorization headers`() {
        val out = Redactor.redact("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature")
        assertFalse(out.contains("eyJhbGciOiJIUzI1NiJ9.payload.signature"))
    }

    @Test
    fun `redacts inline url credentials`() {
        val out = Redactor.redact("postgres://user:hunter2@db.internal:5432/app")
        assertFalse(out.contains("hunter2"))
    }

    @Test
    fun `mask keeps only last four characters`() {
        assertTrue(Redactor.mask("abcdefgh").endsWith("efgh"))
        assertFalse(Redactor.mask("abcdefgh").contains("abcd"))
    }

    @Test
    fun `leaves benign text untouched`() {
        val text = "organise downloaded PDF files"
        assertTrue(Redactor.redact(text) == text)
    }
}
