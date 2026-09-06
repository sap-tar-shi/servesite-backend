import contextvars

# The single source of truth for "which tenant is this request/task for".
# Async-safe: contextvars automatically isolates values per async task/thread,
# unlike a global variable or thread-local in an ASGI/threaded context.
current_tenant: contextvars.ContextVar = contextvars.ContextVar("current_tenant", default=None)


def set_current_tenant(tenant):
    """Store the resolved Tenant instance (or None) for this request context."""
    return current_tenant.set(tenant)


def get_current_tenant():
    """Retrieve the Tenant instance for the current context, or None if unset."""
    return current_tenant.get()


def reset_current_tenant(token):
    """Reset the context var using the token returned by set_current_tenant."""
    current_tenant.reset(token)