package com.jarvisblue.core.common

/**
 * Logging facade. Implementations in the Android layer redact secrets before writing.
 */
interface AppLogger {
    fun d(tag: String, message: String)
    fun i(tag: String, message: String)
    fun w(tag: String, message: String, error: Throwable? = null)
    fun e(tag: String, message: String, error: Throwable? = null)

    /** Structured audit-grade entry; separate from verbose logs. */
    fun audit(tag: String, message: String)
}

object NoopLogger : AppLogger {
    override fun d(tag: String, message: String) = Unit
    override fun i(tag: String, message: String) = Unit
    override fun w(tag: String, message: String, error: Throwable?) = Unit
    override fun e(tag: String, message: String, error: Throwable?) = Unit
    override fun audit(tag: String, message: String) = Unit
}
