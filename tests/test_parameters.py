"""The parameters of an operation, given on the command line.

The command line of ``netforge run`` takes the parameters of the operation
as flags.  These tests are about the parsing and the coercion: the
operation itself is never run, because the suite is offline.
"""

from __future__ import annotations

import pytest

from netforge.adapters.parameters import (
    ParameterError,
    the_flags,
    the_payload,
    the_type_of,
)


class TestTheFlags:
    """The arguments argparse did not know are the parameters."""

    def test_a_flag_and_a_value(self):
        assert the_flags(["--host", "192.168.0.13"]) == {"host": "192.168.0.13"}

    def test_a_flag_with_an_equal_sign(self):
        assert the_flags(["--host=192.168.0.13"]) == {"host": "192.168.0.13"}

    def test_several_flags(self):
        flags = the_flags(["--host", "1.2.3.4", "--port", "22"])
        assert flags == {"host": "1.2.3.4", "port": "22"}

    def test_a_dash_in_a_name_is_an_underscore(self):
        assert the_flags(["--client-keys", "/tmp/key"]) == {"client_keys": "/tmp/key"}

    def test_a_flag_without_a_value(self):
        assert the_flags(["--verbose"]) == {"verbose": None}

    def test_a_flag_without_a_value_before_another_flag(self):
        assert the_flags(["--verbose", "--host", "1.2.3.4"]) == {
            "verbose": None,
            "host": "1.2.3.4",
        }

    def test_an_argument_that_is_not_a_flag_is_refused(self):
        with pytest.raises(ParameterError, match="unexpected argument"):
            the_flags(["host"])


class TestTheType:
    """The type comes from the request schema of the operation."""

    def test_a_string(self):
        assert the_type_of({"type": "string"}) == "string"

    def test_an_integer(self):
        assert the_type_of({"type": "integer"}) == "integer"

    def test_a_number(self):
        assert the_type_of({"type": "number"}) == "number"

    def test_a_boolean(self):
        assert the_type_of({"type": "boolean"}) == "boolean"

    def test_a_list(self):
        assert the_type_of({"type": "array", "items": {"type": "integer"}}) == (
            "list of integer"
        )

    def test_a_list_of_strings(self):
        assert the_type_of({"type": "array", "items": {"type": "string"}}) == "list"

    def test_a_optional_type_is_the_type_that_is_not_null(self):
        schema = {"anyOf": [{"type": "string"}, {"type": "null"}]}
        assert the_type_of(schema) == "string"

    def test_a_property_without_a_type_is_a_string(self):
        assert the_type_of({}) == "string"


class TestTheCoercion:
    """The value is coerced as a value that came in as JSON would be."""

    def test_a_string_is_left_alone(self):
        assert the_payload({"host": "1.2.3.4"}, {"host": {"type": "string"}}) == {
            "host": "1.2.3.4"
        }

    def test_a_whole_number(self):
        payload = the_payload({"port": "22"}, {"port": {"type": "integer"}})
        assert payload == {"port": 22}

    def test_a_number(self):
        payload = the_payload({"timeout": "2.5"}, {"timeout": {"type": "number"}})
        assert payload == {"timeout": 2.5}

    def test_a_whole_number_that_is_not_one_is_refused(self):
        with pytest.raises(ParameterError, match="whole number"):
            the_payload({"port": "abc"}, {"port": {"type": "integer"}})

    def test_a_number_that_is_not_one_is_refused(self):
        with pytest.raises(ParameterError, match="must be a number"):
            the_payload({"timeout": "soon"}, {"timeout": {"type": "number"}})

    def test_a_boolean_that_is_given_alone_is_true(self):
        payload = the_payload({"verbose": None}, {"verbose": {"type": "boolean"}})
        assert payload == {"verbose": True}

    def test_a_boolean_that_is_given_is_read(self):
        payload = the_payload({"verbose": "false"}, {"verbose": {"type": "boolean"}})
        assert payload == {"verbose": False}

    def test_a_boolean_that_is_nonsense_is_refused(self):
        with pytest.raises(ParameterError, match="true or false"):
            the_payload({"verbose": "maybe"}, {"verbose": {"type": "boolean"}})

    def test_a_list_written_as_json(self):
        schema = {"type": "array", "items": {"type": "integer"}}
        payload = the_payload({"ports": "[22, 80]"}, {"ports": schema})
        assert payload == {"ports": [22, 80]}

    def test_a_list_written_with_commas(self):
        schema = {"type": "array", "items": {"type": "integer"}}
        payload = the_payload({"ports": "22,80"}, {"ports": schema})
        assert payload == {"ports": [22, 80]}

    def test_a_list_of_words(self):
        schema = {"type": "array", "items": {"type": "string"}}
        payload = the_payload({"tags": "a,b"}, {"tags": schema})
        assert payload == {"tags": ["a", "b"]}

    def test_a_list_that_is_not_a_list_is_refused(self):
        schema = {"type": "array", "items": {"type": "integer"}}
        with pytest.raises(ParameterError, match="whole numbers"):
            the_payload({"ports": "a,b"}, {"ports": schema})

    def test_an_object_written_as_json(self):
        schema = {"type": "object"}
        payload = the_payload({"options": '{"a": 1}'}, {"options": schema})
        assert payload == {"options": {"a": 1}}

    def test_a_parameter_that_needs_a_value_and_has_none_is_refused(self):
        with pytest.raises(ParameterError, match="needs a value"):
            the_payload({"host": None}, {"host": {"type": "string"}})


class TestTheRefusal:
    """A parameter that the operation does not have is refused."""

    def test_an_unknown_parameter_is_refused(self):
        with pytest.raises(ParameterError, match="unknown parameter"):
            the_payload({"hosst": "1.2.3.4"}, {"host": {"type": "string"}})

    def test_the_refusal_names_the_parameters_there_are(self):
        with pytest.raises(ParameterError, match="host, ports"):
            the_payload({"nope": "1"}, {"host": {"type": "string"}, "ports": {"type": "array"}})
