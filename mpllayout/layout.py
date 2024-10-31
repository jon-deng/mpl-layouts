"""
Classes for handling collections of primitives and constraints

The strategy to solve a collection of constraints is to use three labelled
lists representing a system of non-linear equations:
    `primitives: `
        A collection of `geo.Primitive` instances

        These represent the unknowns parameters of the geometric system and is
        represented as a tree.
    `constraints: tp.List[geo.Constraint]`
        A list of `geo.Constraint` instances representing the non-linear
        equations

        Each `geo.Constraint.assem_res' represents the non-linear equation(s)
        that must be satisfied for the constraint.
    `constraint_graph: StrGraph`
        A graph linking each constraint to the primitives in `primitives`
        (through string labels) the constraint applies to

The class `Layout` handles construction of these three things while functions
`solve` and `solve_linear` use the layout to solve the system of constraints.
"""

import typing as tp
from numpy.typing import NDArray

import warnings

import numpy as np

from . import geometry as geo
from .containers import Node, ItemCounter, iter_flat, flatten, unflatten

IntGraph = tp.List[tp.Tuple[int, ...]]
StrGraph = tp.List[tp.Tuple[str, ...]]


class Layout:
    """
    A constrained layout of primitives

    The class holds a collection of primitives, constraints on those primitives, and the
    graph between constraints and primitives they apply to.

    Parameters
    ----------
    root_prim:
        A `Node` container of `geo.Primitive`s
    constraints:
        A list of constraints
    constraint_graph:
        A list of keys indicating which primitives each constraint applies to
    """

    def __init__(
        self,
        root_prim: tp.Optional[geo.PrimitiveNode] = None,
        root_constraint: tp.Optional[geo.ConstraintNode] = None,
        root_constraint_graph: tp.Optional[geo.PrimKeysNode] = None,
        root_constraint_param: tp.Optional[geo.PrimParamsNode] = None,
        constraint_key_counter: tp.Optional[ItemCounter] = None,
    ):

        if root_prim is None:
            root_prim = geo.PrimitiveNode(np.array([]), {})
        if root_constraint is None:
            root_constraint = geo.ConstraintNode(None, {})
        if root_constraint_graph is None:
            root_constraint_graph = geo.PrimKeysNode(None, {})
        if root_constraint_param is None:
            root_constraint_param = geo.PrimParamsNode(None, {})
        if constraint_key_counter is None:
            constraint_key_counter = ItemCounter()

        self._root_prim = root_prim
        self._root_constraint = root_constraint
        self._root_constraint_graph = root_constraint_graph
        self._root_constraint_param = root_constraint_param

        self._constraint_key_counter = constraint_key_counter

    @property
    def root_prim(self):
        return self._root_prim

    @property
    def root_constraint(self):
        return self._root_constraint

    @property
    def root_constraint_graph(self):
        return self._root_constraint_graph

    @property
    def root_constraint_param(self) -> Node[str, Node]:
        return self._root_constraint_param

    def flat_constraints(self):
        # The `[1:]` removes the 'root' constraint which is just a container
        constraints = [
            node for _, node in iter_flat('', self.root_constraint)
        ][1:]
        constraints_argkeys = [
            node.value for _, node in iter_flat('', self.root_constraint_graph)
        ][1:]
        constraints_param = [
            node.value for _, node in iter_flat('', self.root_constraint_param)
        ][1:]

        constraints = [c.assem_res_atleast_1d for c in constraints]


        return constraints, constraints_argkeys, constraints_param

    def add_prim(self, prim: geo.Primitive, key: str):
        """
        Add a primitive to the layout

        The primitive will be added to `self.root_prim` under the given `key`.

        Parameters
        ----------
        prim: geo.Primitive
            The primitive to add
        key: str
            The key for the primitive
        """
        self.root_prim.add_child(key, prim)

    def add_constraint(
        self,
        constraint: geo.Constraint,
        prim_keys: tp.Tuple[str, ...],
        param: tp.Tuple[tp.Any],
        key: str = ""
    ):
        """
        Add a constraint between primitives

        Parameters
        ----------
        constraint:
            The constraint to apply
        prim_labels:
            A tuple of strings referencing primitives (`self.root_prim`)
        """
        nodes = (
            self.root_constraint,
            self.root_constraint_graph,
            self.root_constraint_param
        )
        if key == "":
            key = self._constraint_key_counter.add_item_to_nodes(constraint, *nodes)
        self.root_constraint.add_child(key, constraint)
        self.root_constraint_graph.add_child(key, constraint.root_argkeys(prim_keys))
        self.root_constraint_param.add_child(key, constraint.root_param(param))

def build_prim_graph(
    root_prim: geo.Primitive,
) -> tp.Tuple[tp.Mapping[str, int], tp.List[geo.Primitive]]:
    """
    Return a map from flat keys to indices in a list of unique primitives
    """
    prims = list(set(prim for _, prim in iter_flat("", root_prim)))
    prim_to_idx = {prim: ii for ii, prim in enumerate(prims)}

    prim_graph = {key: prim_to_idx[prim] for key, prim in iter_flat("", root_prim)}

    return prim_graph, prims


def build_tree(
    root_prim: geo.Primitive, prim_graph: tp.Mapping[str, int], values: tp.List[NDArray]
) -> geo.Primitive:
    """
    Return a new tree where child node values have been updated

    Parameters
    ----------
    root_prim:
        The old tree
    prim_graph:
        A mapping from keys in `root_prim` to corresponding new values in `values`
    values:
        A list of new parameter values to build a new tree with

    Returns
    -------
    Node
        The new tree with values from `values`
    """
    old_prim_structs = flatten("", root_prim)

    # `key[1:]` remove the initial forward slash from the flat keys
    new_prim_values = [values[prim_graph[key]] for key, _ in iter_flat("", root_prim)]

    new_prim_structs = [
        (*old_struct[:2], new_value, *old_struct[3:])
        for old_struct, new_value in zip(old_prim_structs, new_prim_values)
    ]
    return unflatten(new_prim_structs)[0]


import matplotlib as mpl
from matplotlib.axes import Axes
from matplotlib.axis import Axis, XAxis, YAxis


def update_layout_constraints(
        root_constraint: Node,
        root_constraint_param: Node,
        axs: tp.Mapping[str, Axes]
    ) -> Node:
    # Update constraints based on bboxes
    from mpllayout.containers import Node

    # Update x/y axis bbox dimensions
    for ax_key, ax in axs.items():
        dims = get_axis_bbox_dims(ax.xaxis)
        root_constraint_param = update_bbox_dimension_constraints(
           root_constraint, root_constraint_param, f"{ax_key}.XAxis", *dims
        )

        dims = get_axis_bbox_dims(ax.yaxis)
        root_constraint_param = update_bbox_dimension_constraints(
            root_constraint, root_constraint_param, f"{ax_key}.YAxis", *dims
        )
    return root_constraint_param


def update_bbox_dimension_constraints(
    root_constraint: Node,
    root_constraint_param: Node,
    bbox_key: str,
    width: float,
    height: float,
) -> Node:
    dims = (width, height)
    dim_labels = ("Width", "Height")
    constraint_labels = [f"{bbox_key}.{dim_label}" for dim_label in dim_labels]
    for dim_label, dim in zip(constraint_labels, dims):
        if dim_label in root_constraint_param:
            constraint = root_constraint[dim_label]
            root_constraint_param[dim_label] = constraint.root_param((dim,))
        else:
            warnings.warn(f"'{bbox_key}' is missing a '{dim_label}' constraint")

    return root_constraint_param


def get_axis_bbox_dims(axis: Axis):

    axis_bbox = axis.get_tightbbox()
    if axis_bbox is None:
        return (0, 0)
    else:
        axis_bbox = axis_bbox.transformed(axis.axes.figure.transFigure.inverted())
        fig_width, fig_height = axis.axes.figure.get_size_inches()
        axes_bbox = axis.axes.get_position()
        if isinstance(axis, XAxis):
            width = axes_bbox.width * fig_width
            if axis.get_ticks_position() == "bottom":
                height = fig_height * (axes_bbox.ymin - axis_bbox.ymin)
            if axis.get_ticks_position() == "top":
                height = fig_height * (axis_bbox.ymax - axes_bbox.ymax)
        elif isinstance(axis, YAxis):
            height = axes_bbox.height * fig_height
            if axis.get_ticks_position() == "left":
                width = fig_width * (axes_bbox.xmin - axis_bbox.xmin)
            if axis.get_ticks_position() == "right":
                width = fig_width * (axis_bbox.xmax - axes_bbox.xmax)
        else:
            raise TypeError

        return width, height
