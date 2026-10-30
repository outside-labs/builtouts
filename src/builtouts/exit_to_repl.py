import code
import inspect
import types


PRIMITIVES = (int, float, str, bool, bytes, list, dict, set, tuple, type(None))


def _get_callable_sig(func_or_mtd):
    """Extract a clean signature string for any callable, stripping 'self' and 'cls'."""
    try:
        sig = inspect.signature(func_or_mtd)
        params = [
            str(p) for name, p in sig.parameters.items()
            if name not in ("self", "cls")
        ]
        return f"({', '.join(params)})"
    except (ValueError, TypeError):
        return "()"


def build_repl_banner(namespace: object):
    blocks = []
    skip = {"build_repl_banner", "drop_to_repl", "_get_callable_sig", "PRIMITIVES"}

    items = {
        k: v for k, v in namespace.items()
        if not k.startswith("__") and k not in skip and not isinstance(v, types.ModuleType)
    }

    # 1. Class Definitions
    for name, obj in items.items():
        if inspect.isclass(obj):
            lines = [f"{name}{_get_callable_sig(obj.__init__)}"]
            for m_name, m_obj in inspect.getmembers(obj, predicate=inspect.isfunction):
                if not m_name.startswith("_"):
                    lines.append(f"\tmtd: {m_name}{_get_callable_sig(m_obj)}")
            blocks.append("\n".join(lines))

    # 2. Instantiated Class Objects
    for name, obj in items.items():
        if not inspect.isclass(obj) and not inspect.isroutine(obj) and not isinstance(obj, PRIMITIVES):
            cls_name = type(obj).__name__
            lines = [f"{name} -> {cls_name}{_get_callable_sig(type(obj).__init__)}"]

            if hasattr(obj, "__dict__"):
                for attr, val in vars(obj).items():
                    if not attr.startswith("_"):
                        lines.append(f"\tattr: {attr}={repr(val)}")

            for m_name, m_obj in inspect.getmembers(obj, predicate=inspect.ismethod):
                if not m_name.startswith("_"):
                    lines.append(f"\tmtd: {m_name}{_get_callable_sig(m_obj)}")

            blocks.append("\n".join(lines))

    # 3. Standalone Functions
    for name, obj in items.items():
        if inspect.isfunction(obj):
            blocks.append(f"func: {name}{_get_callable_sig(obj)}")

    # 4. Standard Variables (Primitives & Collections)
    for name, obj in items.items():
        if isinstance(obj, PRIMITIVES):
            blocks.append(f"{name}={repr(obj)}")

    return "\n\n".join(blocks)


def exit_to_repl():
    """Drop into a REPL with the caller's exact globals and locals."""
    frame = inspect.currentframe()
    try:
        caller = frame.f_back
        ns = {**caller.f_globals, **caller.f_locals}
    finally:
        # Explicitly delete frame references to avoid reference cycles
        del frame
        del caller

    return code.interact(banner=build_repl_banner(ns), local=ns)
