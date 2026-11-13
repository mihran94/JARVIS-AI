package com.jarvisblue.core.common

/**
 * Minimal result type so domain code never leaks exceptions across module boundaries.
 */
sealed interface Outcome<out T> {
    data class Success<T>(val value: T) : Outcome<T>
    data class Failure(val error: AppError) : Outcome<Nothing>

    val valueOrNull: T? get() = (this as? Success)?.value
    val errorOrNull: AppError? get() = (this as? Failure)?.error
    val isSuccess: Boolean get() = this is Success
}

sealed class AppError(override val message: String, cause: Throwable? = null) : Exception(message, cause) {
    class Network(message: String, cause: Throwable? = null) : AppError(message, cause)
    class Unauthorized(message: String = "Authentication required") : AppError(message)
    class NotConfigured(message: String) : AppError(message)
    class RateLimited(message: String, val retryAfterSeconds: Int = 0) : AppError(message)
    class InvalidInput(message: String) : AppError(message)
    class PermissionDenied(message: String) : AppError(message)
    class NotSupported(message: String) : AppError(message)
    class Timeout(message: String, cause: Throwable? = null) : AppError(message)
    class Unexpected(message: String, cause: Throwable? = null) : AppError(message)
}

inline fun <T, R> Outcome<T>.map(transform: (T) -> R): Outcome<R> = when (this) {
    is Outcome.Success -> Outcome.Success(transform(value))
    is Outcome.Failure -> this
}

inline fun <T> Outcome<T>.onSuccess(action: (T) -> Unit): Outcome<T> {
    if (this is Outcome.Success) action(value)
    return this
}

inline fun <T> Outcome<T>.onFailure(action: (AppError) -> Unit): Outcome<T> {
    if (this is Outcome.Failure) action(error)
    return this
}

fun <T> runCatchingOutcome(block: () -> T): Outcome<T> = try {
    Outcome.Success(block())
} catch (t: Throwable) {
    if (t is AppError) Outcome.Failure(t)
    else Outcome.Failure(AppError.Unexpected(t.message ?: "Unexpected failure", t))
}

/** Suspending variant of [runCatchingOutcome]. */
suspend inline fun <T> runCatchingOutcomeSuspend(crossinline block: suspend () -> T): Outcome<T> = try {
    Outcome.Success(block())
} catch (t: Throwable) {
    if (t is AppError) Outcome.Failure(t)
    else Outcome.Failure(AppError.Unexpected(t.message ?: "Unexpected failure", t))
}
