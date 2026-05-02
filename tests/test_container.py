"""
ASD v12.0 — Unit tests for DI ServiceContainer.
"""
import pytest
from src.core.container import ServiceContainer, ServiceNotRegisteredError, container


class TestServiceContainer:
    """Unit tests for ServiceContainer."""

    def test_register_and_resolve_returns_same_instance(self):
        """resolve() returns the identical singleton on repeated calls."""
        svc = ServiceContainer()

        class Foo:
            pass

        svc.register(Foo, lambda: Foo())
        a = svc.resolve(Foo)
        b = svc.resolve(Foo)
        assert a is b
        assert isinstance(a, Foo)

    def test_register_instance_uses_provided_instance(self):
        """register_instance() stores the exact object given."""
        svc = ServiceContainer()

        class Foo:
            pass

        foo = Foo()
        svc.register_instance(Foo, foo)
        assert svc.resolve(Foo) is foo

    def test_lazy_creation_calls_factory_once(self):
        """Factory is called exactly once, only on first resolve()."""
        svc = ServiceContainer()
        calls = []

        class Foo:
            pass

        svc.register(Foo, lambda: (calls.append(1), Foo())[1])
        assert len(calls) == 0
        svc.resolve(Foo)
        assert len(calls) == 1
        svc.resolve(Foo)
        assert len(calls) == 1

    def test_resolve_unregistered_raises(self):
        """Resolving an unregistered type raises ServiceNotRegisteredError."""
        svc = ServiceContainer()

        class Unknown:
            pass

        with pytest.raises(ServiceNotRegisteredError, match="Unknown"):
            svc.resolve(Unknown)

    def test_override_injects_mock(self):
        """override() makes resolve() return the mock instead."""
        svc = ServiceContainer()

        class Foo:
            pass

        real = Foo()
        mock = object()
        svc.register_instance(Foo, real)
        assert svc.resolve(Foo) is real

        svc.override(Foo, mock)
        assert svc.resolve(Foo) is mock

    def test_reset_overrides_restores_original(self):
        """After override + reset_overrides, resolve returns original."""
        svc = ServiceContainer()

        class Foo:
            pass

        real = Foo()
        mock = object()
        svc.register_instance(Foo, real)
        svc.override(Foo, mock)
        svc.reset_overrides()
        assert svc.resolve(Foo) is real

    def test_reset_clears_everything(self):
        """reset() clears registry, overrides, and factories."""
        svc = ServiceContainer()

        class Foo:
            pass

        svc.register(Foo, lambda: Foo())
        svc.resolve(Foo)
        svc.override(Foo, object())
        svc.reset()

        with pytest.raises(ServiceNotRegisteredError):
            svc.resolve(Foo)

    def test_is_initialized_flag(self):
        """_initialized flag tracks state."""
        svc = ServiceContainer()
        assert not svc.is_initialized
        svc._initialized = True
        assert svc.is_initialized

    def test_module_level_container_exists(self):
        """The module-level 'container' singleton is a ServiceContainer."""
        assert isinstance(container, ServiceContainer)
