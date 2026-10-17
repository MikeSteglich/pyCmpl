""" sets, parameters and the cmpl data generated from them - no CMPL binary needed """

import pytest

from pyCmpl import CmplSet, CmplParameter, CmplException


def test_enumeration_set():
    s = CmplSet("S")
    s.setValues(["a", "b", 3])
    assert s.values == ["a", "b", 3]
    assert s.len == 3
    assert s.count() == 3


def test_tuple_set_values_are_tuples():
    s = CmplSet("A", 2)
    s.setValues([(1, "p"), [2, "q"]])
    assert s.values == [(1, "p"), (2, "q")]
    assert s.len == 2


def test_tuple_set_rank_mismatch():
    with pytest.raises(CmplException):
        CmplSet("A", 2).setValues([(1, 2, 3)])


@pytest.mark.parametrize("args, values", [
    ((1, 5), [1, 2, 3, 4, 5]),
    ((1, 2, 9), [1, 3, 5, 7, 9]),
    ((9, -2, 1), [9, 7, 5, 3, 1]),
])
def test_algorithmic_sets(args, values):
    s = CmplSet("N")
    s.setValues(*args)
    assert s.values == values
    assert s.len == len(values)
    assert s.count() == len(values)


def test_large_range_set_len_is_cheap():
    s = CmplSet("N")
    s.setValues(1, 10 ** 8)
    assert s.len == 10 ** 8


@pytest.mark.parametrize("args", [(5, 1), (1, 0, 9), (1, 2, 1), (9, -1, 10), (1.0, 5)])
def test_invalid_algorithmic_sets(args):
    with pytest.raises(CmplException):
        CmplSet("N").setValues(*args)


def test_invalid_set_name():
    with pytest.raises(CmplException):
        CmplSet("a b")


def test_parameter_list_dimension():
    s = CmplSet("I")
    s.setValues([1, 2, 3])
    p = CmplParameter("c", s)
    p.setValues([3, 1, 2])
    assert p.values == [3, 1, 2]
    with pytest.raises(CmplException):
        p.setValues([1, 2])


def test_parameter_dense_dict_dimension():
    s = CmplSet("I")
    s.setValues([1, 2, 3])
    with pytest.raises(CmplException):
        CmplParameter("c", s).setValues({1: 3, 2: 1})


def test_parameter_sparse_dict_with_default():
    s = CmplSet("I")
    s.setValues([1, 2, 3])
    p = CmplParameter("c", s)
    p.setValues({1: 3}, 0)
    assert p.defaultValue == 0


@pytest.mark.parametrize("default", [[1], {"a": 1}, (1, 2)])
def test_parameter_invalid_default_value(default):
    s = CmplSet("I")
    s.setValues([1, 2, 3])
    with pytest.raises(CmplException):
        CmplParameter("c", s).setValues({1: 3}, default)


def test_scalar_parameter():
    p = CmplParameter("b")
    p.setValues(10)
    assert p.value == 10
    with pytest.raises(CmplException):
        p.setValues([10])
