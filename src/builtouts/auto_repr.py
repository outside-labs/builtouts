from reprlib import recursive_repr
from typing import Iterable, Optional, Type, TypeVar

T = TypeVar("T")


def auto_repr(
        cls: Optional[Type[T]] = None,
        *,
        public_only: bool = True,
        exclude: Iterable[str] = (),
        include: Iterable[str] = (),
        fillvalue: str = "...",
) -> Type[T]:
    """
    Class decorator that generates a namedtuple-style __repr__.

    Args:
        public_only: If True, omits attributes starting with '_' (and '__' mangled names).
        exclude: Attribute names to always omit (supports unmangled '__name' too).
        include: Extra attributes or @property names to explicitly include, or force-include
                 even when public_only=True.
        fillvalue: Placeholder string used when a circular reference is detected.
    """
    exclude_set = frozenset(exclude)
    include_tuple = tuple(include)

    def wrap(target_cls: Type[T]) -> Type[T]:
        @recursive_repr(fillvalue=fillvalue)
        def __repr__(self) -> str:
            instance_cls = type(self)
            fields = {}

            # 1. Walk MRO (base classes first) to gather all __slots__
            for base in reversed(instance_cls.__mro__):
                slots = getattr(base, "__slots__", ())
                if isinstance(slots, str):
                    slots = (slots,)

                base_prefix = f"_{base.__name__.lstrip('_')}__"
                for slot in slots:
                    if slot in ("__dict__", "__weakref__"):
                        continue
                    # Handle double-underscore name mangling inside __slots__
                    attr_name = (
                        f"{base_prefix}{slot[2:]}"
                        if slot.startswith("__") and not slot.endswith("__")
                        else slot
                    )
                    if hasattr(self, attr_name):
                        fields[attr_name] = getattr(self, attr_name)

            # 2. Gather standard __dict__ attributes (if the class or subclass has one)
            if hasattr(self, "__dict__"):
                fields.update(self.__dict__)

            # 3. Apply public_only and exclude filters
            filtered = {}
            for k, v in fields.items():
                if k in exclude_set:
                    continue
                if public_only and k.startswith("_") and k not in include_tuple:
                    continue
                filtered[k] = v

            # 4. Append explicitly included attributes (e.g., @property or specific private attrs)
            for name in include_tuple:
                if name not in filtered and name not in exclude_set and hasattr(self, name):
                    filtered[name] = getattr(self, name)

            attrs = ", ".join(f"{k}={v!r}" for k, v in filtered.items())
            return f"{instance_cls.__name__}({attrs})"

        # Preserve proper function metadata for introspection / debugging
        __repr__.__qualname__ = f"{target_cls.__qualname__}.__repr__"
        __repr__.__module__ = target_cls.__module__
        target_cls.__repr__ = __repr__
        return target_cls

    # Allow both @auto_repr and @auto_repr(...)
    return wrap(cls) if cls is not None else wrap