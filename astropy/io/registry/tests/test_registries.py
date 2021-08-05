# -*- coding: utf-8 -*-
# Licensed under a 3-clause BSD style license - see LICENSE.rst

"""
Test :mod:`astropy.io.registry`.

.. todo::

    Don't rely on Table for tests

"""

import contextlib
import os
from collections import Counter
from copy import copy, deepcopy
from io import StringIO

import pytest

import numpy as np

import astropy.units as u
from astropy.io import registry as io_registry
from astropy.io.registry import (IORegistryError, UnifiedInputRegistry,
                                 UnifiedIORegistry, UnifiedOutputRegistry, compat)
from astropy.io.registry.compat import default_registry
from astropy.io.registry.core import UnifiedIORegistryBase
from astropy.table import Table

###############################################################################
# pytest setup and fixtures


class UnifiedIORegistryBaseSubClass(UnifiedIORegistryBase):
    """Non-abstract subclass of UnifiedIORegistryBase for testing."""

    def get_formats(self, data_class=None):
        return None


class EmptyData:
    """
    Thing that can read and write.
    Note that the read/write are the compatibility methods, which allow for the
    kwarg ``registry``. This allows us to not subclass ``EmptyData`` for each
    of the types of registry (read-only, ...) and use this class everywhere.
    """

    read = classmethod(io_registry.read)
    write = io_registry.write


class OtherEmptyData:
    """A different class with different I/O"""

    read = classmethod(io_registry.read)
    write = io_registry.write


def empty_reader(*args, **kwargs):
    return EmptyData()


def empty_writer(table, *args, **kwargs):
    pass


def empty_identifier(*args, **kwargs):
    return True


@pytest.fixture
def fmtcls1():
    return ("test1", EmptyData)


@pytest.fixture
def fmtcls2():
    return ("test2", EmptyData)


@pytest.fixture(params=["test1", "test2"])
def fmtcls(request):
    yield (request.param, EmptyData)


@pytest.fixture
def original():
    ORIGINAL = {}
    ORIGINAL["readers"] = deepcopy(default_registry._readers)
    ORIGINAL["writers"] = deepcopy(default_registry._writers)
    ORIGINAL["identifiers"] = deepcopy(default_registry._identifiers)
    return ORIGINAL


###############################################################################


def test_fmcls1_fmtcls2(fmtcls1, fmtcls2):
    """Just check a fact that we rely on in other tests."""
    assert fmtcls1[1] is fmtcls2[1]


def test_IORegistryError():

    with pytest.raises(IORegistryError, match="just checking"):
        raise IORegistryError("just checking")


class TestUnifiedIORegistryBase:
    """Test :class:`astropy.io.registry.UnifiedIORegistryBase`."""

    def setup_class(self):
        """Setup class. This is called 1st by pytest."""
        self._cls = UnifiedIORegistryBaseSubClass

    @pytest.fixture
    def registry(self):
        """I/O registry. Cleaned before and after each function."""
        registry = self._cls()

        HAS_READERS = hasattr(registry, "_readers")
        HAS_WRITERS = hasattr(registry, "_writers")

        # copy and clear original registry
        ORIGINAL = {}
        ORIGINAL["identifiers"] = copy(registry._identifiers)
        registry._identifiers.clear()
        if HAS_READERS:
            ORIGINAL["readers"] = copy(registry._readers)
            registry._readers.clear()
        if HAS_WRITERS:
            ORIGINAL["writers"] = copy(registry._writers)
            registry._writers.clear()

        yield registry

        registry._identifiers.clear()
        registry._identifiers.update(ORIGINAL["identifiers"])
        if HAS_READERS:
            registry._readers.clear()
            registry._readers.update(ORIGINAL["readers"])
        if HAS_WRITERS:
            registry._writers.clear()
            registry._writers.update(ORIGINAL["writers"])

    # ===========================================

    def test_get_formats(self, registry):
        """Test ``registry.get_formats()``."""
        # defaults
        assert registry.get_formats() is None
        # (kw)args don't matter
        assert registry.get_formats(data_class=24) is None

    def test_delay_doc_updates(self, registry, fmtcls1, recwarn):
        """Test ``registry.delay_doc_updates()``."""
        # TODO! figure out what can be tested
        with registry.delay_doc_updates(EmptyData):
            registry.register_identifier(*fmtcls1, empty_identifier)

    def test_register_identifier(self, registry, fmtcls1, fmtcls2):
        """Test ``registry.register_identifier()``."""
        # initial check it's not registered
        assert fmtcls1 not in registry._identifiers
        assert fmtcls2 not in registry._identifiers

        # register
        registry.register_identifier(*fmtcls1, empty_identifier)
        registry.register_identifier(*fmtcls2, empty_identifier)
        assert fmtcls1 in registry._identifiers
        assert fmtcls2 in registry._identifiers

    def test_register_identifier_invalid(self, registry, fmtcls):
        """Test calling ``registry.register_identifier()`` twice."""
        fmt, cls = fmtcls
        registry.register_identifier(fmt, cls, empty_identifier)
        with pytest.raises(IORegistryError) as exc:
            registry.register_identifier(fmt, cls, empty_identifier)
        assert (
            str(exc.value) == f"Identifier for format '{fmt}' and class "
            f"'{cls.__name__}' is already defined"
        )

    def test_register_identifier_force(self, registry, fmtcls1):
        registry.register_identifier(*fmtcls1, empty_identifier)
        registry.register_identifier(*fmtcls1, empty_identifier, force=True)
        assert fmtcls1 in registry._identifiers

    def test_unregister_identifier(self, registry, fmtcls1):
        """Test ``registry.unregister_identifier()``."""
        registry.register_identifier(*fmtcls1, empty_identifier)
        assert fmtcls1 in registry._identifiers

        registry.unregister_identifier(*fmtcls1)
        assert fmtcls1 not in registry._identifiers

    def test_unregister_identifier_invalid(self, registry, fmtcls):
        """Test ``registry.unregister_identifier()``."""
        fmt, cls = fmtcls
        with pytest.raises(IORegistryError) as exc:
            registry.unregister_identifier(fmt, cls)
        assert (
            str(exc.value) == f"No identifier defined for format '{fmt}' "
            f"and class '{cls.__name__}'"
        )

    def test_identify_format(self, registry):
        """Test ``registry.identify_format()``."""
        args = (None, EmptyData, None, None, (None,), dict())

        # test no formats to identify
        formats = registry.identify_format(*args)
        assert formats == []

        # test there is a format to identify
        registry.register_identifier("test", EmptyData, empty_identifier)
        formats = registry.identify_format(*args)
        assert "test" in formats

    # ===========================================
    # Compat tests

    def test_compat_register_identifier(self, registry, fmtcls1):
        # with registry specified
        assert fmtcls1 not in registry._identifiers
        compat.register_identifier(*fmtcls1, empty_identifier, registry=registry)
        assert fmtcls1 in registry._identifiers

        # without registry specified it becomes default_registry
        if registry is not default_registry:
            assert fmtcls1 not in default_registry._identifiers
            try:
                compat.register_identifier(*fmtcls1, empty_identifier)
            except Exception:
                pass
            else:
                assert fmtcls1 in default_registry._identifiers
            finally:
                default_registry._identifiers.pop(fmtcls1)

    @pytest.mark.skip("TODO!")
    def test_compat_unregister_identifier(self, registry, fmtcls1):
        assert False

    @pytest.mark.skip("TODO!")
    def test_compat_identify_format(self, registry, fmtcls1):
        assert False

    @pytest.mark.skip("TODO!")
    def test_compat_get_formats(self, registry, fmtcls1):
        assert False

    @pytest.mark.skip("TODO!")
    def test_compat_delay_doc_updates(self, registry, fmtcls1):
        assert False


class TestUnifiedInputRegistry(TestUnifiedIORegistryBase):
    """Test :class:`astropy.io.registry.UnifiedInputRegistry`."""

    def setup_class(self):
        """Setup class. This is called 1st by pytest."""
        self._cls = UnifiedInputRegistry

    # ===========================================

    def test_inherited_read_registration(self, registry):
        # check that multi-generation inheritance works properly,
        # meaning that a child inherits from parents before
        # grandparents, see astropy/astropy#7156

        class Child1(EmptyData):
            pass

        class Child2(Child1):
            pass

        def _read():
            return EmptyData()

        def _read1():
            return Child1()

        # check that reader gets inherited
        registry.register_reader("test", EmptyData, _read)
        assert registry.get_reader("test", Child2) is _read

        # check that nearest ancestor is identified
        # (i.e. that the reader for Child2 is the registered method
        #  for Child1, and not Table)
        registry.register_reader("test", Child1, _read1)
        assert registry.get_reader("test", Child2) is _read1

    # ===========================================

    @pytest.mark.skip("TODO!")
    def test_get_formats(self, registry):
        """Test ``registry.get_formats()``."""
        assert False

    def test_delay_doc_updates(self, registry, fmtcls1, recwarn):
        """Test ``registry.delay_doc_updates()``.

        capture and ignore warnings with ``recwarn``. Empty registries
        emit a FutureWarning and there's a race condition when other
        tests are run simultaneously.
        """
        super().test_delay_doc_updates(registry, fmtcls1, recwarn)

        with registry.delay_doc_updates(EmptyData):
            registry.register_reader("test", EmptyData, empty_reader)

            # test that the doc has not yet been updated.
            # if a the format was registered in a different way, then
            # test that this method is not present.
            if "Format" in EmptyData.read.__doc__:
                docs = EmptyData.read.__doc__.split("\n")
                ifmt = docs[8].index("Format") + 1
                iread = docs[8].index("Read") + 1
                # there might not actually be anything here, which is also good
                if docs[9] != docs[10]:
                    assert docs[10][ifmt : ifmt + 5] == "test"
                    assert docs[10][iread : iread + 3] != "Yes"
        # now test it's updated
        docs = EmptyData.read.__doc__.split("\n")
        ifmt = docs[8].index("Format") + 2
        iread = docs[8].index("Read") + 1
        assert docs[10][ifmt : ifmt + 4] == "test"
        assert docs[10][iread : iread + 3] == "Yes"

    def test_identify_read_format(self, registry):
        """Test ``registry.identify_format()``."""
        args = ("read", EmptyData, None, None, (None,), dict())

        # test there is no format to identify
        formats = registry.identify_format(*args)
        assert formats == []

        # test there is a format to identify
        # doesn't actually matter if register a reader, it returns True for all
        registry.register_identifier("test", EmptyData, empty_identifier)
        formats = registry.identify_format(*args)
        assert "test" in formats

    # -----------------------

    def test_register_reader(self, registry, fmtcls1, fmtcls2):
        """Test ``registry.register_reader()``."""
        # initial check it's not registered
        assert fmtcls1 not in registry._readers
        assert fmtcls2 not in registry._readers

        # register
        registry.register_reader(*fmtcls1, empty_reader)
        registry.register_reader(*fmtcls2, empty_reader)
        assert fmtcls1 in registry._readers
        assert fmtcls2 in registry._readers
        assert registry._readers[fmtcls1] == (empty_reader, 0)  # (f, priority)
        assert registry._readers[fmtcls2] == (empty_reader, 0)  # (f, priority)

    def test_register_reader_invalid(self, registry, fmtcls1):
        fmt, cls = fmtcls1
        registry.register_reader(fmt, cls, empty_reader)
        with pytest.raises(IORegistryError) as exc:
            registry.register_reader(fmt, cls, empty_reader)
        assert (
            str(exc.value) == f"Reader for format '{fmt}' and class "
            f"'{cls.__name__}' is already defined"
        )

    def test_register_reader_force(self, registry, fmtcls1):
        registry.register_reader(*fmtcls1, empty_reader)
        registry.register_reader(*fmtcls1, empty_reader, force=True)
        assert fmtcls1 in registry._readers

    def test_register_readers_with_same_name_on_different_classes(
        self, registry, recwarn
    ):
        # No errors should be generated if the same name is registered for
        # different objects...but this failed under python3
        registry.register_reader("test", EmptyData, lambda: EmptyData())
        registry.register_reader("test", OtherEmptyData, lambda: OtherEmptyData())
        t = EmptyData.read(format="test", registry=registry)
        assert isinstance(t, EmptyData)
        tbl = OtherEmptyData.read(format="test", registry=registry)
        assert isinstance(tbl, OtherEmptyData)

    # -----------------------

    def test_unregister_reader(self, registry, fmtcls1):
        """Test ``registry.unregister_reader()``."""
        registry.register_reader(*fmtcls1, empty_reader)
        assert fmtcls1 in registry._readers

        with pytest.warns(FutureWarning):
            registry.unregister_reader(*fmtcls1)
        assert fmtcls1 not in registry._readers

    def test_unregister_reader_invalid(self, registry, fmtcls1):
        fmt, cls = fmtcls1
        with pytest.raises(IORegistryError) as exc:
            registry.unregister_reader(*fmtcls1)
        assert (
            str(exc.value) == f"No reader defined for format '{fmt}' and "
            f"class '{cls.__name__}'"
        )

    # -----------------------

    def test_get_reader(self, registry, fmtcls):
        """Test ``registry.get_reader()``."""
        fmt, cls = fmtcls
        with pytest.raises(IORegistryError):
            with pytest.warns(FutureWarning):
                registry.get_reader(fmt, cls)

        registry.register_reader(fmt, cls, empty_reader)
        reader = registry.get_reader(fmt, cls)
        assert reader is empty_reader

    def test_get_reader_invalid(self, registry, fmtcls):
        fmt, cls = fmtcls
        with pytest.raises(IORegistryError) as exc:
            with pytest.warns(FutureWarning):
                registry.get_reader(fmt, cls)
        assert str(exc.value).startswith(
            f"No reader defined for format '{fmt}' and class '{cls.__name__}'"
        )

    # -----------------------

    def test_read_noformat(self, registry):
        """Test ``registry.read()`` when there isn't a reader."""
        with pytest.raises(IORegistryError) as exc:
            with pytest.warns(FutureWarning):
                EmptyData.read(registry=registry)
        assert str(exc.value).startswith(
            "Format could not be identified based"
            " on the file name or contents, "
            "please provide a 'format' argument."
        )

    def test_read_noformat_arbitrary(self, registry, original):
        """Test that all identifier functions can accept arbitrary input"""
        registry._identifiers.update(original["identifiers"])
        with pytest.raises(IORegistryError) as exc:
            with pytest.warns(FutureWarning):
                EmptyData.read(object(), registry=registry)
        assert str(exc.value).startswith(
            "Format could not be identified based"
            " on the file name or contents, "
            "please provide a 'format' argument."
        )

    def test_read_noformat_arbitrary_file(self, tmpdir, registry, original):
        """Tests that all identifier functions can accept arbitrary files"""
        registry._readers.update(original["readers"])
        testfile = str(tmpdir.join("foo.example"))
        with open(testfile, "w") as f:
            f.write("Hello world")

        with pytest.raises(IORegistryError) as exc:
            with pytest.warns(FutureWarning):
                Table.read(testfile)
        assert str(exc.value).startswith(
            "Format could not be identified based"
            " on the file name or contents, "
            "please provide a 'format' argument."
        )

    def test_read_toomanyformats(self, registry, fmtcls1, fmtcls2, recwarn):
        fmt1, cls = fmtcls1
        fmt2, _ = fmtcls2

        registry.register_identifier(fmt1, cls, lambda o, *x, **y: True)
        registry.register_identifier(fmt2, cls, lambda o, *x, **y: True)
        with pytest.raises(IORegistryError) as exc:
            cls.read(registry=registry)
        assert str(exc.value) == (f"Format is ambiguous - options are: {fmt1}, {fmt2}")

    def test_read_uses_priority(self, registry, fmtcls1, fmtcls2, recwarn):
        fmt1, cls = fmtcls1
        fmt2, _ = fmtcls2
        counter = Counter()

        def counting_reader1(*args, **kwargs):
            counter[fmt1] += 1
            return cls()

        def counting_reader2(*args, **kwargs):
            counter[fmt2] += 1
            return cls()

        registry.register_reader(fmt1, cls, counting_reader1, priority=1)
        registry.register_reader(fmt2, cls, counting_reader2, priority=2)
        registry.register_identifier(fmt1, cls, lambda o, *x, **y: True)
        registry.register_identifier(fmt2, cls, lambda o, *x, **y: True)

        cls.read(registry=registry)
        assert counter[fmt2] == 1
        assert counter[fmt1] == 0

    def test_read_format_noreader(self, registry, fmtcls1):
        fmt, cls = fmtcls1
        with pytest.raises(IORegistryError) as exc:
            with pytest.warns(FutureWarning):
                cls.read(format=fmt, registry=registry)
        assert str(exc.value).startswith(
            f"No reader defined for format '{fmt}' and class '{cls.__name__}'"
        )

    def test_read_identifier(self, tmpdir, registry, fmtcls1, fmtcls2, recwarn):
        fmt1, cls = fmtcls1
        fmt2, _ = fmtcls2

        registry.register_identifier(
            fmt1, cls, lambda o, path, fileobj, *x, **y: path.endswith("a")
        )
        registry.register_identifier(
            fmt2, cls, lambda o, path, fileobj, *x, **y: path.endswith("b")
        )

        # Now check that we got past the identifier and are trying to get
        # the reader. The registry.get_reader will fail but the error message
        # will tell us if the identifier worked.

        filename = tmpdir.join("testfile.a").strpath
        open(filename, "w").close()
        with pytest.raises(IORegistryError) as exc:
            cls.read(filename, registry=registry)
        assert str(exc.value).startswith(
            f"No reader defined for format '{fmt1}' and class '{cls.__name__}'"
        )

        filename = tmpdir.join("testfile.b").strpath
        open(filename, "w").close()
        with pytest.raises(IORegistryError) as exc:
            with pytest.warns(FutureWarning):
                cls.read(filename, registry=registry)
        assert str(exc.value).startswith(
            f"No reader defined for format '{fmt2}' and class '{cls.__name__}'"
        )

    def test_read_valid_return(self, registry, fmtcls):
        fmt, cls = fmtcls
        registry.register_reader(fmt, cls, lambda: cls())
        t = cls.read(format=fmt, registry=registry)
        assert isinstance(t, cls)

    def test_read_non_existing_unknown_ext(self, fmtcls1):
        """Raise the correct error when attempting to read a non-existing
        file with an unknown extension."""
        with pytest.raises(OSError):
            data = fmtcls1[1].read("non-existing-file-with-unknown.ext")

    def test_read_directory(self, tmpdir, registry):
        """
        Regression test for a bug that caused the I/O registry infrastructure to
        not work correctly for datasets that are represented by folders as
        opposed to files, when using the descriptors to add read/write methods.
        """

        registry.register_identifier(
            "test_folder_format", EmptyData, lambda o, *x, **y: o == "read"
        )
        registry.register_reader("test_folder_format", EmptyData, empty_reader)

        filename = tmpdir.mkdir("folder_dataset").strpath

        # With the format explicitly specified
        dataset = EmptyData.read(
            filename, format="test_folder_format", registry=registry
        )
        assert isinstance(dataset, EmptyData)

        # With the auto-format identification
        dataset = EmptyData.read(filename, registry=registry)
        assert isinstance(dataset, EmptyData)

    # ===========================================
    # Compat tests

    @pytest.mark.skip("TODO!")
    def test_compat_register_reader(self, registry, fmtcls1):
        assert False

    @pytest.mark.skip("TODO!")
    def test_compat_unregister_reader(self, registry, fmtcls1):
        assert False

    @pytest.mark.skip("TODO!")
    def test_compat_get_reader(self, registry, fmtcls1):
        assert False

    @pytest.mark.skip("TODO!")
    def test_compat_read(self, registry, fmtcls1):
        assert False


class TestUnifiedOutputRegistry(TestUnifiedIORegistryBase):
    """Test :class:`astropy.io.registry.UnifiedOutputRegistry`."""

    def setup_class(self):
        """Setup class. This is called 1st by pytest."""
        self._cls = UnifiedOutputRegistry

    # ===========================================

    def test_inherited_write_registration(self, registry):
        # check that multi-generation inheritance works properly,
        # meaning that a child inherits from parents before
        # grandparents, see astropy/astropy#7156

        class Child1(EmptyData):
            pass

        class Child2(Child1):
            pass

        def _write():
            return EmptyData()

        def _write1():
            return Child1()

        # check that writer gets inherited
        registry.register_writer("test", EmptyData, _write)
        assert registry.get_writer("test", Child2) is _write

        # check that nearest ancestor is identified
        # (i.e. that the writer for Child2 is the registered method
        #  for Child1, and not Table)
        registry.register_writer("test", Child1, _write1)
        assert registry.get_writer("test", Child2) is _write1

    # ===========================================

    def test_delay_doc_updates(self, registry, fmtcls1, recwarn):
        """Test ``registry.delay_doc_updates()``.

        capture and ignore warnings with ``recwarn``. Empty registries
        emit a FutureWarning and there's a race condition when other
        tests are run simultaneously.
        """
        super().test_delay_doc_updates(registry, fmtcls1, recwarn)

        with registry.delay_doc_updates(EmptyData):
            registry.register_writer("test", EmptyData, empty_writer)

            # test that the doc has not yet been updated.
            # if a the format was registered in a different way, then
            # test that this method is not present.
            if "Format" in EmptyData.read.__doc__:
                docs = EmptyData.write.__doc__.split("\n")
                ifmt = docs[8].index("Format") + 1
                iwrite = docs[8].index("Write") + 1
                # there might not actually be anything here, which is also good
                if docs[9] != docs[10]:
                    assert docs[10][ifmt : ifmt + 5] == "test"
                    assert docs[10][iwrite : iwrite + 3] != "Yes"
        # now test it's updated
        docs = EmptyData.write.__doc__.split("\n")
        ifmt = docs[8].index("Format") + 2
        iwrite = docs[8].index("Write") + 2
        assert docs[10][ifmt : ifmt + 4] == "test"
        assert docs[10][iwrite : iwrite + 3] == "Yes"

    @pytest.mark.skip("TODO!")
    def test_get_formats(self, registry):
        """Test ``registry.get_formats()``."""
        assert False

    def test_identify_write_format(self, registry):
        """Test ``registry.identify_format()``."""
        args = ("write", EmptyData, None, None, (None,), dict())

        # test there is no format to identify
        formats = registry.identify_format(*args)
        assert formats == []

        # test there is a format to identify
        # doesn't actually matter if register a writer, it returns True for all
        registry.register_identifier("test", EmptyData, empty_identifier)
        formats = registry.identify_format(*args)
        assert "test" in formats

    # -----------------------

    def test_register_writer(self, registry, fmtcls1, fmtcls2):
        """Test ``registry.register_writer()``."""
        # initial check it's not registered
        assert fmtcls1 not in registry._writers
        assert fmtcls2 not in registry._writers

        # register
        registry.register_writer(*fmtcls1, empty_writer)
        registry.register_writer(*fmtcls2, empty_writer)
        assert fmtcls1 in registry._writers
        assert fmtcls2 in registry._writers

    def test_register_writer_invalid(self, registry, fmtcls):
        """Test calling ``registry.register_writer()`` twice."""
        fmt, cls = fmtcls
        registry.register_writer(fmt, cls, empty_writer)
        with pytest.raises(IORegistryError) as exc:
            registry.register_writer(fmt, cls, empty_writer)
        assert (
            str(exc.value) == f"Writer for format '{fmt}' and class "
            f"'{cls.__name__}' is already defined"
        )

    def test_register_writer_force(self, registry, fmtcls1):
        registry.register_writer(*fmtcls1, empty_writer)
        registry.register_writer(*fmtcls1, empty_writer, force=True)
        assert fmtcls1 in registry._writers

    # -----------------------

    def test_unregister_writer(self, registry, fmtcls1):
        """Test ``registry.unregister_writer()``."""
        registry.register_writer(*fmtcls1, empty_writer)
        assert fmtcls1 in registry._writers

        with pytest.warns(FutureWarning):
            registry.unregister_writer(*fmtcls1)
        assert fmtcls1 not in registry._writers

    def test_unregister_writer_invalid(self, registry, fmtcls):
        """Test ``registry.unregister_writer()``."""
        fmt, cls = fmtcls
        with pytest.raises(IORegistryError) as exc:
            registry.unregister_writer(fmt, cls)
        assert (
            str(exc.value) == f"No writer defined for format '{fmt}' "
            f"and class '{cls.__name__}'"
        )

    # -----------------------

    def test_get_writer(self, registry, recwarn):
        """Test ``registry.get_writer()``."""
        with pytest.raises(IORegistryError):
            registry.get_writer("test", EmptyData)

        registry.register_writer("test", EmptyData, empty_writer)
        writer = registry.get_writer("test", EmptyData)
        assert writer is empty_writer

    def test_get_writer_invalid(self, registry, fmtcls1, recwarn):
        """Test invalid ``registry.get_writer()``."""
        fmt, cls = fmtcls1
        with pytest.raises(IORegistryError) as exc:
            registry.get_writer(fmt, cls)
        assert str(exc.value).startswith(
            f"No writer defined for format '{fmt}' and class '{cls.__name__}'"
        )

    # -----------------------

    def test_write_noformat(self):
        """Test ``registry.write()`` when there isn't a writer."""
        with pytest.raises(IORegistryError) as exc:
            with pytest.warns(FutureWarning):
                EmptyData().write()
        assert str(exc.value).startswith(
            "Format could not be identified based"
            " on the file name or contents, "
            "please provide a 'format' argument."
        )

    def test_write_noformat_arbitrary(self, registry, original):
        """Test that all identifier functions can accept arbitrary input"""
        registry._identifiers.update(original["identifiers"])
        with pytest.raises(IORegistryError) as exc:
            with pytest.warns(FutureWarning):
                EmptyData().write(object())
        assert str(exc.value).startswith(
            "Format could not be identified based"
            " on the file name or contents, "
            "please provide a 'format' argument."
        )

    def test_write_noformat_arbitrary_file(self, tmpdir, registry, original, recwarn):
        """Tests that all identifier functions can accept arbitrary files"""
        registry._writers.update(original["writers"])
        testfile = str(tmpdir.join("foo.example"))

        with pytest.raises(IORegistryError) as exc:
            Table().write(testfile, registry=registry)
        assert str(exc.value).startswith(
            "Format could not be identified based"
            " on the file name or contents, "
            "please provide a 'format' argument."
        )

    def test_write_toomanyformats(self, registry, fmtcls1, fmtcls2):
        registry.register_identifier(*fmtcls1, lambda o, *x, **y: True)
        registry.register_identifier(*fmtcls2, lambda o, *x, **y: True)
        with pytest.raises(IORegistryError) as exc:
            fmtcls1[1]().write(registry=registry)
        assert str(exc.value) == (
            f"Format is ambiguous - options are: {fmtcls1[0]}, {fmtcls2[0]}"
        )

    def test_write_uses_priority(self, registry, fmtcls1, fmtcls2, recwarn):
        fmt1, cls1 = fmtcls1
        fmt2, cls2 = fmtcls2
        counter = Counter()

        def counting_writer1(*args, **kwargs):
            counter[fmt1] += 1

        def counting_writer2(*args, **kwargs):
            counter[fmt2] += 1

        registry.register_writer(fmt1, cls1, counting_writer1, priority=1)
        registry.register_writer(fmt2, cls2, counting_writer2, priority=2)
        registry.register_identifier(fmt1, cls1, lambda o, *x, **y: True)
        registry.register_identifier(fmt2, cls2, lambda o, *x, **y: True)

        cls1().write(registry=registry)
        assert counter[fmt2] == 1
        assert counter[fmt1] == 0

    def test_write_format_nowriter(self, registry, fmtcls1):
        fmt, cls = fmtcls1
        with pytest.raises(IORegistryError) as exc:
            with pytest.warns(FutureWarning):
                cls().write(format=fmt, registry=registry)
        assert str(exc.value).startswith(
            f"No writer defined for format '{fmt}' and class '{cls.__name__}'"
        )

    def test_write_identifier(self, registry, fmtcls1, fmtcls2, recwarn):
        fmt1, cls = fmtcls1
        fmt2, _ = fmtcls2

        registry.register_identifier(fmt1, cls, lambda o, *x, **y: x[0].startswith("a"))
        registry.register_identifier(fmt2, cls, lambda o, *x, **y: x[0].startswith("b"))

        # Now check that we got past the identifier and are trying to get
        # the reader. The registry.get_writer will fail but the error message
        # will tell us if the identifier worked.

        with pytest.raises(IORegistryError) as exc:
            cls().write("abc", registry=registry)
        assert str(exc.value).startswith(
            f"No writer defined for format '{fmt1}' and class '{cls.__name__}'"
        )

        with pytest.raises(IORegistryError) as exc:
            cls().write("bac", registry=registry)
        assert str(exc.value).startswith(
            f"No writer defined for format '{fmt2}' and class '{cls.__name__}'"
        )

    def test_write_return(self, registry, fmtcls1):
        """Most writers will return None, but other values are not forbidden."""
        fmt, cls = fmtcls1
        registry.register_writer(fmt, cls, lambda *args: True)
        res = cls.write(cls(), format=fmt, registry=registry)
        assert res is True

    # ===========================================
    # Compat tests

    @pytest.mark.skip("TODO!")
    def test_compat_register_writer(self, registry, fmtcls1):
        assert False

    @pytest.mark.skip("TODO!")
    def test_compat_unregister_writer(self, registry, fmtcls1):
        assert False

    @pytest.mark.skip("TODO!")
    def test_compat_get_writer(self, registry, fmtcls1):
        assert False

    @pytest.mark.skip("TODO!")
    def test_compat_write(self, registry, fmtcls1):
        assert False


class TestUnifiedIORegistry(TestUnifiedInputRegistry, TestUnifiedOutputRegistry):
    def setup_class(self):
        """Setup class. This is called 1st by pytest."""
        self._cls = UnifiedIORegistry

    # ===========================================

    @pytest.mark.skip("TODO!")
    def test_get_formats(self, registry):
        """Test ``registry.get_formats()``."""
        assert False

    def test_delay_doc_updates(self, registry, fmtcls1, recwarn):
        """Test ``registry.delay_doc_updates()``.

        capture and ignore warnings with ``recwarn``. Empty registries
        emit a FutureWarning and there's a race condition when other
        tests are run simultaneously.
        """
        super().test_delay_doc_updates(registry, fmtcls1, recwarn)

    # -----------------------

    def test_identifier_origin(self, registry, fmtcls1, fmtcls2):
        fmt1, cls = fmtcls1
        fmt2, _ = fmtcls2

        registry.register_identifier(fmt1, cls, lambda o, *x, **y: o == "read")
        registry.register_identifier(fmt2, cls, lambda o, *x, **y: o == "write")
        registry.register_reader(fmt1, cls, empty_reader)
        registry.register_writer(fmt2, cls, empty_writer)

        # There should not be too many formats defined
        cls.read(registry=registry)
        cls().write(registry=registry)

        with pytest.raises(IORegistryError) as exc:
            cls.read(format=fmt2, registry=registry)
        assert str(exc.value).startswith(
            f"No reader defined for format '{fmt2}' and class '{cls.__name__}'"
        )

        with pytest.raises(IORegistryError) as exc:
            cls().write(format=fmt1, registry=registry)
        assert str(exc.value).startswith(
            f"No writer defined for format '{fmt1}' and class '{cls.__name__}'"
        )


class TestDefaultRegistry(TestUnifiedIORegistry):
    def setup_class(self):
        """Setup class. This is called 1st by pytest."""
        self._cls = lambda *args: default_registry


# =============================================================================
# Test compat
# much of this is already tested above since EmptyData uses io_registry.X(),
# which are the compat methods.


def test_dir():
    """Test all the compat methods are in the directory"""
    dc = dir(compat)
    for n in compat.__all__:
        assert n in dc


def test_getattr():
    for n in compat.__all__:
        assert hasattr(compat, n)

    with pytest.raises(AttributeError, match="module 'astropy.io.registry.compat'"):
        compat.this_is_definitely_not_in_this_module


# =============================================================================
# Table tests


def test_read_basic_table():
    registry = Table.read._registry
    data = np.array(
        list(zip([1, 2, 3], ["a", "b", "c"])), dtype=[("A", int), ("B", "|U1")]
    )
    try:
        registry.register_reader("test", Table, lambda x: Table(x))
    except Exception:
        pass
    else:
        t = Table.read(data, format="test")
        assert t.keys() == ["A", "B"]
        for i in range(3):
            assert t["A"][i] == data["A"][i]
            assert t["B"][i] == data["B"][i]
    finally:
        registry._readers.pop("test", None)


class TestSubclass:
    """
    Test using registry with a Table sub-class
    """

    @pytest.fixture(autouse=True)
    def registry(self):
        """I/O registry. Not cleaned."""
        yield

    def test_read_table_subclass(self):
        class MyTable(Table):
            pass

        data = ["a b", "1 2"]
        mt = MyTable.read(data, format="ascii")
        t = Table.read(data, format="ascii")
        assert np.all(mt == t)
        assert mt.colnames == t.colnames
        assert type(mt) is MyTable

    def test_write_table_subclass(self):
        buffer = StringIO()

        class MyTable(Table):
            pass

        mt = MyTable([[1], [2]], names=["a", "b"])
        mt.write(buffer, format="ascii")
        assert buffer.getvalue() == os.linesep.join(["a b", "1 2", ""])

    def test_read_table_subclass_with_columns_attributes(self, tmpdir):
        """Regression test for https://github.com/astropy/astropy/issues/7181"""

        class MTable(Table):
            pass

        mt = MTable([[1, 2.5]], names=["a"])
        mt["a"].unit = u.m
        mt["a"].format = ".4f"
        mt["a"].description = "hello"

        testfile = str(tmpdir.join("junk.fits"))
        mt.write(testfile, overwrite=True)

        t = MTable.read(testfile)
        assert np.all(mt == t)
        assert mt.colnames == t.colnames
        assert type(t) is MTable
        assert t["a"].unit == u.m
        assert t["a"].format == "{:13.4f}"
        assert t["a"].description == "hello"
