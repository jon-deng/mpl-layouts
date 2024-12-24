"""
Geometric constraints
"""

from typing import Optional, Any
from numpy.typing import NDArray

from collections import namedtuple
import itertools

import numpy as np
import jax.numpy as jnp

from . import primitives as pr
from .containers import Node, iter_flat, map, accumulate
from . import constructions as con

Primitive = pr.Primitive


ResParams = dict[str, Any]

ResPrims = tuple[Primitive, ...]
ResPrimTypes = tuple[type[Primitive], ...]

PrimKeys = tuple[str, ...]
ChildPrimKeys = tuple[PrimKeys, ...]

def load_named_tuple(
        NamedTuple: namedtuple,
        args: dict[str, Any] | tuple[Any, ...]
    ):
    if isinstance(args, dict):
        args = NamedTuple(**args)
    elif isinstance(args, tuple):
        args = NamedTuple(*args)
    elif isinstance(args, NamedTuple):
        pass
    else:
        raise TypeError()
    return args

PrimKeysNode = con.PrimKeysNode
ParamsNode = con.ParamsNode

# TODO: Add constraint class that accepts a unit
# This would handle the case of setting a length relative to another one

Constraint = con.Construction
ConstraintNode = con.ConstructionNode
ArrayConstraint = con.ArrayConstruction

ChildKeys = tuple[str, ...]
ChildConstraints = tuple[con.ConstructionNode, ...]

## Point constraints
# NOTE: These are actual constraint classes that can be called so class docstrings
# document there `assem_res` function.

def _generate_aux_data_node(
    ConstructionType: type[con.Construction],
    **kwargs
):
    child_keys, child_constructions, child_prims_keys, split_child_params = ConstructionType.init_children(**kwargs)
    children = {
        key: _generate_aux_data_node(type(child))
        for key, child in zip(child_keys, child_constructions)
    }

    aux_data = ConstructionType.init_aux_data(**kwargs)
    return Node(aux_data, children)


def generate_constraint(
    ConstructionType: type[con.Construction],
    constraint_name: str,
    construction_output_size: Optional[Node[int, Node]] = None
):
    if issubclass(ConstructionType, con.CompoundConstruction):
        def derived_assem(prims, derived_params):
            *params, value = derived_params
            return np.array([])
    elif issubclass(ConstructionType, con.LeafConstruction):
        def derived_assem(prims, derived_params):
            *params, value = derived_params
            return ConstructionType.assem(prims, *params) - value
    else:
        raise TypeError()

    class DerivedConstraint(ConstructionType):

        @classmethod
        def init_children(cls, **kwargs):
            child_keys, child_constructions, child_prim_keys, split_child_params = ConstructionType.init_children(**kwargs)

            if construction_output_size is None:
                aux_data_node = _generate_aux_data_node(ConstructionType)

                _construction_output_size = accumulate(
                    lambda x, y: x+y,
                    map(lambda aux_data: aux_data['RES_SIZE'], aux_data_node),
                    0
                )
            else:
                _construction_output_size = construction_output_size

            derived_child_constructions = [
                generate_constraint(
                    type(child_constraint), child_key, _construction_output_size[child_key]
                )()
                for child_key, child_constraint in zip(child_keys, child_constructions)
            ]

            child_res_sizes = [node.value for node in _construction_output_size.values()]
            cum_child_res_sizes = [size for size in itertools.accumulate([0] + child_res_sizes, initial=0)]
            child_value_slices = [
                slice(start,  stop)
                for start, stop in zip(cum_child_res_sizes[:-1], cum_child_res_sizes[1:])
            ]
            def split_value(value):
                if isinstance(value, (float, int)):
                    return len(child_keys) * (value,)
                else:
                    return tuple(value[idx] for idx in child_value_slices)

            def derived_split_child_params(derived_params):
                *params, value = derived_params
                split_params = split_child_params(params)
                _split_value = split_value(value)

                return tuple(
                    (*params, value)
                    for params, value in zip(split_params, _split_value)
                )

            return child_keys, derived_child_constructions, child_prim_keys, derived_split_child_params

        @classmethod
        def init_aux_data(cls, **kwargs):
            aux_data = ConstructionType.init_aux_data(**kwargs)
            derived_aux_data = {
                'RES_ARG_TYPES': aux_data['RES_ARG_TYPES'],
                'RES_PARAMS_TYPE': namedtuple(
                    'Parameters', aux_data['RES_PARAMS_TYPE']._fields+('value',)
                ),
                'RES_SIZE': aux_data['RES_SIZE']
            }
            return derived_aux_data

        @classmethod
        def assem(cls, prims, *derived_params):
            return derived_assem(prims, derived_params)

    DerivedConstraint.__name__ = constraint_name

    return DerivedConstraint


# Argument type: tuple[Point,]

Fix = generate_constraint(con.Coordinate, 'Fix')

# Argument type: tuple[Point, Point]

DirectedDistance = generate_constraint(con.DirectedDistance, 'DirectedDistance')

XDistance = generate_constraint(con.XDistance, 'XDistance')

YDistance = generate_constraint(con.YDistance, 'YDistance')

class Coincident(con.LeafConstruction):
    """
    Constrain two points to be coincident

    Parameters
    ----------
    prims: tuple[pr.Point, pr.Point]
        The two points
    """

    @classmethod
    def init_aux_data(cls):
        return {
            'RES_ARG_TYPES': (pr.Point, pr.Point),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ())
        }

    @classmethod
    def assem(cls, prims: tuple[pr.Point, pr.Point]):
        """
        Return the coincident error between two points
        """
        point0, point1 = prims
        return con.Coordinate.assem((point1,)) - con.Coordinate.assem((point0,))


## Line constraints

# Argument type: tuple[Line,]

Length = generate_constraint(con.Length, 'Length')

DirectedLength = generate_constraint(con.DirectedLength, 'DirectedLength')

XLength = generate_constraint(con.XLength, 'XLength')

YLength = generate_constraint(con.YLength, 'YLength')


class Vertical(con.LeafConstruction):
    """
    Constrain a line to be vertical

    Parameters
    ----------
    prims: tuple[pr.Line]
        The lines
    """

    @classmethod
    def init_aux_data(cls):
        return {
            'RES_ARG_TYPES': (pr.Line,),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ())
        }

    @classmethod
    def assem(cls, prims: tuple[pr.Line]):
        return jnp.dot(con.LineVector.assem(prims), np.array([1, 0]))


class Horizontal(con.LeafConstruction):
    """
    Constrain a line to be horizontal

    Parameters
    ----------
    prims: tuple[pr.Line]
        The lines
    """

    @classmethod
    def init_aux_data(cls):
        return {
            'RES_ARG_TYPES': (pr.Line,),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ())
        }

    @classmethod
    def assem(cls, prims: tuple[pr.Line]):
        return jnp.dot(con.LineVector.assem(prims), np.array([0, 1]))


# Argument type: tuple[Line, Line]

class RelativeLength(con.LeafConstruction):
    """
    Constrain the length of a line relative to another line

    Parameters
    ----------
    prims: tuple[pr.Line, pr.Line]
        The lines

        The length of the first line is measured relative to the second line
    length: float
        The relative length
    """

    @classmethod
    def init_aux_data(cls):
        return {
            'RES_ARG_TYPES': (pr.Line, pr.Line),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ("length",))
        }

    @classmethod
    def assem(cls, prims: tuple[pr.Line, pr.Line], length: float):
        """
        Return the length error of line `prims[0]` relative to line `prims[1]`
        """
        # This sets the length of a line
        line0, line1 = prims
        vec_a = con.LineVector.assem((line0,))
        vec_b = con.LineVector.assem((line1,))
        return jnp.sum(vec_a**2) - length**2 * jnp.sum(vec_b**2)

MidpointXDistance = generate_constraint(con.MidpointXDistance, 'MidpointXDistance')

MidpointYDistance = generate_constraint(con.MidpointYDistance, 'MidpointYDistance')

class Orthogonal(con.LeafConstruction):
    """
    Constrain two lines to be orthogonal

    Parameters
    ----------
    prims: tuple[pr.Line, pr.Line]
        The lines
    """

    @classmethod
    def init_aux_data(cls):
        return {
            'RES_ARG_TYPES': (pr.Line, pr.Line),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ())
        }

    @classmethod
    def assem(cls, prims: tuple[pr.Line, pr.Line]):
        """
        Return the orthogonal error between two lines
        """
        line0, line1 = prims
        return jnp.dot(
            con.LineVector.assem((line0,)), con.LineVector.assem((line1,))
        )


class Parallel(con.LeafConstruction):
    """
    Return the parallel error between two lines

    Parameters
    ----------
    prims: tuple[pr.Line, pr.Line]
        The lines
    """

    @classmethod
    def init_aux_data(cls):
        return {
            'RES_ARG_TYPES': (pr.Line, pr.Line),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ())
        }

    @classmethod
    def assem(cls, prims: tuple[pr.Line, pr.Line]):
        """
        Return the parallel error between two lines
        """
        line0, line1 = prims
        return jnp.cross(
            con.LineVector.assem((line0,)), con.LineVector.assem((line1,))
        )


Angle = generate_constraint(con.Angle, 'Angle')


class Collinear(con.LeafConstruction):
    """
    Return the collinear error between two lines

    Parameters
    ----------
    prims: tuple[pr.Line, pr.Line]
        The lines
    """

    @classmethod
    def init_aux_data(cls):
        return {
            'RES_ARG_TYPES': (pr.Line, pr.Line),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ())
        }

    @classmethod
    def assem(self, prims: tuple[pr.Line, pr.Line]):
        """
        Return the collinearity error between two lines
        """
        line0, line1 = prims
        line2 = pr.Line(prims=(line1[0], line0[0]))

        return jnp.array(
            [Parallel.assem((line0, line1)), Parallel.assem((line0, line2))]
        )


class CoincidentLines(con.LeafConstruction):
    """
    Return coincident error between two lines

    Parameters
    ----------
    prims: tuple[pr.Line, pr.Line]
        The lines
    reverse: bool
        A boolean indicating whether lines are reversed
    """

    @classmethod
    def init_aux_data(cls):
        return {
            'RES_ARG_TYPES': (pr.Line, pr.Line),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ("reverse",))
        }

    @classmethod
    def assem(cls, prims: tuple[pr.Line, pr.Line], reverse: bool):
        """
        Return the coincident error between two lines
        """
        line0, line1 = prims
        if reverse:
            point0_err = Coincident.assem((line1['Point0'], line0['Point1']))
            point1_err = Coincident.assem((line1['Point1'], line0['Point0']))
        else:
            point0_err = Coincident.assem((line1['Point0'], line0['Point0']))
            point1_err = Coincident.assem((line1['Point1'], line0['Point1']))
        return jnp.concatenate([point0_err, point1_err])

# Argument type: tuple[Line, ...]

class RelativeLengthArray(ArrayConstraint):
    """
    Constrain the lengths of a set of lines relative to the last

    Parameters
    ----------
    prims: tuple[pr.Line, ...]
        The lines

        The length of the lines are measured relative to the last line
    lengths: NDArray
        The relative lengths
    """

    @classmethod
    def init_children(cls, shape: tuple[int, ...]):
        size = np.prod(shape)

        child_keys = tuple(f"RelativeLength{n}" for n in range(size))
        child_constraints = (size) * (RelativeLength(),)
        child_prim_keys = tuple((f"arg{n}", f"arg{size}") for n in range(size))

        def propogate_child_params(parameters):
            lengths, = parameters
            return tuple(
                (length,) for length in lengths
            )
        return child_keys, child_constraints, child_prim_keys,propogate_child_params

    @classmethod
    def init_aux_data(cls, shape: tuple[int, ...]):
        size = np.prod(shape)
        return {
            'RES_ARG_TYPES': size * (pr.Line,) + (pr.Line,),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ("lengths",))
        }

    @classmethod
    def assem(cls, prims: tuple[pr.Line, ...], lengths: NDArray):
        return np.array([])


class MidpointXDistanceArray(ArrayConstraint):
    """
    Constrain the x-distances between a set of line midpoints

    Parameters
    ----------
    prims: tuple[pr.Line, ...]
        The lines

        The distances are measured from the first to the second line in pairs
    distances: NDArray
        The distances
    """

    @classmethod
    def init_children(cls, shape: tuple[int, ...]):
        num_child = np.prod(shape)

        child_prim_keys = tuple((f"arg{2*n}", f"arg{2*n+1}") for n in range(num_child))
        child_keys = tuple(f"LineMidpointXDistance{n}" for n in range(num_child))
        child_constraints = num_child * (MidpointXDistance(),)
        def propogate_child_params(params):
            distances, = params
            return tuple((distance,) for distance in distances)
        return child_keys, child_constraints, child_prim_keys, propogate_child_params

    @classmethod
    def init_aux_data(cls, shape: tuple[int, ...]):
        num_child = np.prod(shape)
        return {
            'RES_ARG_TYPES': num_child * (pr.Line, pr.Line),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ("distances",))
        }

    @classmethod
    def assem(cls, prims: tuple[pr.Line, ...], distances: NDArray):
        return np.array(())


class MidpointYDistanceArray(ArrayConstraint):
    """
    Constrain the y-distances between a set of line midpoints

    Parameters
    ----------
    prims: tuple[pr.Line, ...]
        The lines

        The distances are measured from the first to the second line in pairs
    distances: NDArray
        The distances
    """

    @classmethod
    def init_children(cls, shape: tuple[int, ...]):
        num_child = np.prod(shape)

        child_prim_keys = tuple((f"arg{2*n}", f"arg{2*n+1}") for n in range(num_child))
        child_keys = tuple(f"LineMidpointYDistance{n}" for n in range(num_child))
        child_constraints = num_child * (MidpointYDistance(),)
        def propogate_child_params(params):
            distances, = params
            return tuple((distance,) for distance in distances)
        return child_keys, child_constraints, child_prim_keys, propogate_child_params

    @classmethod
    def init_aux_data(cls, shape: tuple[int, ...]):
        num_child = np.prod(shape)
        return {
            'RES_ARG_TYPES': num_child * (pr.Line, pr.Line),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ("distances",))
        }

    @classmethod
    def assem(cls, prims: tuple[pr.Line, ...], distances: NDArray):
        return np.array(())


class CollinearArray(ArrayConstraint):
    """
    Constrain a set of lines to be collinear

    Parameters
    ----------
    prims: tuple[pr.Line, ...]
        The lines
    """

    @classmethod
    def init_children(cls, shape: tuple[int, ...]):
        size = np.prod(shape)

        child_prim_keys = tuple(("arg0", f"arg{n}") for n in range(1, size))
        child_keys = tuple(f"Collinear[0][{n}]" for n in range(1, size))
        child_constraints = size * (Collinear(),)
        def propogate_child_constraints(params):
            return size*[()]
        return child_keys, child_constraints, child_prim_keys, propogate_child_constraints

    @classmethod
    def init_aux_data(cls, shape: tuple[int, ...]):
        size = np.prod(shape)
        return {
            'RES_ARG_TYPES': size * (pr.Line, ),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ())
        }

    @classmethod
    def assem(cls, prims: tuple[pr.Line, ...]):
        return np.array([])

## Point and Line constraints

# TODO: class BoundPointsByLine(DynamicConstraint)
# A class that ensures all points have orthogonal distance to a line > offset
# The orthogonal direction should be rotated 90 degrees from the line direction
# (or some other convention)
# You should also have some convention to specify whether you bound for positive
# distance or negative distance
# This would be like saying the points all lie to the left or right of the line
# + and offset
# This would be useful for aligning axis labels

PointOnLineDistance = generate_constraint(con.PointOnLineDistance, 'PointOnLineDistance')

PointToLineDistance = generate_constraint(con.PointToLineDistance, 'PointToLineDistance')


class RelativePointOnLineDistance(con.LeafConstruction):
    """
    Constrain the projected distance of a point along a line

    Parameters
    ----------
    prims: tuple[pr.Point, pr.Line]
        The point and line
    distance: float
    reverse: bool
        A boolean indicating whether to reverse the line direction

        The distance of the point on the line is measured either from the start or end
        point of the line based on `reverse`. If `reverse=False` then the start point is
        used.
    """

    @classmethod
    def init_aux_data(cls):
        return {
            'RES_ARG_TYPES': (pr.Point, pr.Line),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ("distance", "reverse"))
        }

    @classmethod
    def assem(
        cls,
        prims: tuple[pr.Point, pr.Line],
        reverse: bool,
        distance: float
    ):
        """
        Return the projected distance error of a point along a line
        """
        point, line = prims
        if reverse:
            origin = con.Coordinate.assem((line['Point1'],))
            unit_vec = -con.UnitLineVector.assem((line,))
        else:
            origin = con.Coordinate.assem((line['Point0'],))
            unit_vec = con.UnitLineVector.assem((line,))
        line_length = con.Length.assem((line,))

        proj_dist = jnp.dot(point.value-origin, unit_vec)
        return jnp.array([proj_dist - distance*line_length])


## Quad constraints

# Argument type: tuple[Quadrilateral]

class Box(con.StaticConstruction):
    """
    Constrain a quadrilateral to be rectangular

    Parameters
    ----------
    prims: tuple[pr.Quadrilateral]
        The quad
    """

    @classmethod
    def init_children(cls):
        child_keys = ("HorizontalBottom", "HorizontalTop", "VerticalLeft", "VerticalRight")
        child_constraints = (Horizontal(), Horizontal(), Vertical(), Vertical())
        child_prim_keys = (("arg0/Line0",), ("arg0/Line2",), ("arg0/Line3",), ("arg0/Line1",))
        def propagate_child_params(params):
            return [(), (), (), ()]
        return child_keys, child_constraints, child_prim_keys, propagate_child_params

    @classmethod
    def init_aux_data(cls):
        return {
            'RES_ARG_TYPES': (pr.Quadrilateral,),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ())
        }


AspectRatio = generate_constraint(con.AspectRatio, 'AspectRatio')

# Argument type: tuple[Quadrilateral, Quadrilateral]

OuterMargin = generate_constraint(con.OuterMargin, 'OuterMargin')

InnerMargin = generate_constraint(con.InnerMargin, 'InnerMargin')

# Argument type: tuple[Quadrilateral, ...]

def idx_1d(multi_idx: tuple[int, ...], shape: tuple[int, ...]):
    """
    Return a 1D array index from a multi-dimensional array index
    """
    strides = shape[1:] + (1,)
    return sum(axis_idx * stride for axis_idx, stride in zip(multi_idx, strides))

class RectilinearGrid(ArrayConstraint):
    """
    Constrain a set of quads to lie on a rectilinear grid

    Parameters
    ----------
    prims: tuple[pr.Quadrilateral, ...]
        The quadrilaterals
    """

    @classmethod
    def init_children(cls, shape: tuple[int, ...]):
        size = np.prod(shape)
        num_row, num_col = shape

        def idx(i, j):
            return idx_1d((i, j), shape)

        # Specify child constraints given the grid shape
        # Line up bottom/top and left/right
        child_constraints = (
            2 * num_row * (CollinearArray(num_col),)
            + 2 * num_col * (CollinearArray(num_row),)
        )
        align_bottom = [
            tuple(f"arg{idx(nrow, ncol)}/Line0" for ncol in range(num_col))
            for nrow in range(num_row)
        ]
        align_top = [
            tuple(f"arg{idx(nrow, ncol)}/Line2" for ncol in range(num_col))
            for nrow in range(num_row)
        ]
        align_left = [
            tuple(f"arg{idx(nrow, ncol)}/Line3" for nrow in range(num_row))
            for ncol in range(num_col)
        ]
        align_right = [
            tuple(f"arg{idx(nrow, ncol)}/Line1" for nrow in range(num_row))
            for ncol in range(num_col)
        ]
        child_prim_keys = align_bottom + align_top + align_left + align_right
        child_keys = (
            [f"CollinearRowBottom{nrow}" for nrow in range(num_row)]
            + [f"CollinearRowTop{nrow}" for nrow in range(num_row)]
            + [f"CollinearColumnLeft{ncol}" for ncol in range(num_col)]
            + [f"CollinearColumnRight{ncol}" for ncol in range(num_col)]
        )
        def propogate_child_params(params):
            return len(child_keys)*[()]
        return child_keys, child_constraints, child_prim_keys, propogate_child_params

    @classmethod
    def init_aux_data(cls, shape: tuple[int, ...]):
        size = np.prod(shape)
        return {
            'RES_ARG_TYPES': size * (pr.Quadrilateral,),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ())
        }

    @classmethod
    def assem(cls, prims: tuple[pr.Quadrilateral, ...]):
        return np.array(())


class Grid(ArrayConstraint):
    """
    Constrain a set of quads to lie on a dimensioned rectilinear grid

    Parameters
    ----------
    prims: tuple[pr.Quadrilateral, ...]
        The quadrilaterals
    col_widths: NDArray
        Column widths (from left to right) relative to the left-most column
    row_heights: NDArray
        Row height (from top to bottom) relative to the top-most row
    col_margins: NDArray
        Absolute column margins (from left to right)
    row_margins: NDArray
        Absolute row margins (from top to bottom)
    """

    @classmethod
    def init_children(cls, shape: tuple[int, ...]):
        num_args = np.prod(shape)
        num_row, num_col = shape

        # Children constraints do:
        # 1. Align all quads in a grid
        # 2. Set relative column widths relative to column 0
        # 3. Set relative row heights relative to row 0
        child_keys = (
            "RectilinearGrid",
            "ColumnWidths",
            "RowHeights",
            "ColumnMargins",
            "RowMargins",
        )
        child_constraints = (
            RectilinearGrid(shape),
            RelativeLengthArray(num_col-1),
            RelativeLengthArray(num_row-1),
            MidpointXDistanceArray(num_col-1),
            MidpointYDistanceArray(num_row-1),
        )

        def idx(i, j):
            return idx_1d((i, j), shape)
        rows, cols = list(range(shape[0])), list(range(shape[1]))

        rectilineargrid_args = tuple(f"arg{n}" for n in range(num_args))

        colwidth_args = tuple(
            f"arg{idx(row, col)}/Line0"
            for row, col in itertools.product([0], cols[1:] + cols[:1])
        )
        rowheight_args = tuple(
            f"arg{idx(row, col)}/Line1"
            for row, col in itertools.product(rows[1:] + rows[:1], [0])
        )
        col_margin_line_labels = itertools.chain.from_iterable(
            (f"arg{idx(0, col)}/Line1", f"arg{idx(0, col+1)}/Line3")
            for col in cols[:-1]
        )
        row_margin_line_labels = itertools.chain.from_iterable(
            (f"arg{idx(row+1, 0)}/Line2", f"arg{idx(row, 0)}/Line0")
            for row in rows[:-1]
        )

        child_prim_keys = (
            rectilineargrid_args,
            colwidth_args,
            rowheight_args,
            tuple(col_margin_line_labels),
            tuple(row_margin_line_labels),
        )

        def propogate_child_params(params):
            # col_widths, row_heights, col_margins, row_margins = param3s
            return [()] + [(value,) for value in params]

        return child_keys, child_constraints, child_prim_keys, propogate_child_params


    @classmethod
    def init_aux_data(cls, shape: tuple[int, ...]):
        size = np.prod(shape)
        return {
            'RES_ARG_TYPES': size * (pr.Quadrilateral,),
            'RES_PARAMS_TYPE': namedtuple(
                "Parameters",
                ("col_widths", "row_heights", "col_margins", "row_margins")
            )
        }

    @classmethod
    def assem(
        cls,
        prims: tuple[pr.Quadrilateral, ...],
        col_widths: NDArray,
        row_heights: NDArray,
        col_margins: NDArray,
        row_margins: NDArray
    ):
        return np.array([])


## Axes constraints

from matplotlib.axis import XAxis, YAxis

# Argument type: tuple[Quadrilateral]

def get_axis_dim(axis: XAxis | YAxis, side: str):

    # Ignore the axis label in the height by temporarily making it invisible
    label_visibility = axis.label.get_visible()
    axis.label.set_visible(False)

    axis_bbox = axis.get_tightbbox()

    if axis_bbox is None:
        dim = 0
    else:
        axis_bbox = axis_bbox.transformed(axis.axes.figure.transFigure.inverted())
        fig_width, fig_height = axis.axes.figure.get_size_inches()
        axes_bbox = axis.axes.get_position()

        if axis.get_ticks_position() == "bottom":
            dim = fig_height * (axes_bbox.ymin - axis_bbox.ymin)
        elif axis.get_ticks_position() == "top":
            dim = fig_height * (axis_bbox.ymax - axes_bbox.ymax)
        elif axis.get_ticks_position() == "left":
            dim = fig_width * (axes_bbox.xmin - axis_bbox.xmin)
        elif axis.get_ticks_position() == "right":
            dim = fig_width * (axis_bbox.xmax - axes_bbox.xmax)
        else:
            raise ValueError()

    axis.label.set_visible(label_visibility)

    return dim

class XAxisHeight(con.StaticConstruction):
    """
    Return the x-axis height for an axes

    Parameters
    ----------
    prims: tuple[pr.Quadrilateral]
        The axes
    axis: XAxis
        The XAxis
    """

    @staticmethod
    def get_xaxis_height(axis: XAxis):
        return get_axis_dim(axis, axis.get_ticks_position())

    @classmethod
    def init_children(cls):
        child_keys = ("Height",)
        child_constraints = (YDistance(),)
        child_prim_keys = (("arg0/Line1/Point0", "arg0/Line1/Point1"),)

        def propogate_child_params(parameters):
            xaxis: XAxis | None
            xaxis, = parameters
            if xaxis is None:
                return [(0,)]
            else:
                return [(cls.get_xaxis_height(xaxis),)]

        return child_keys, child_constraints, child_prim_keys, propogate_child_params

    @classmethod
    def init_aux_data(cls):
        return {
            'RES_ARG_TYPES': (pr.Quadrilateral,),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ('axis',))
        }


class YAxisWidth(con.StaticConstruction):
    """
    Constrain the y-axis width for an axes

    Parameters
    ----------
    prims: tuple[pr.Quadrilateral]
        The axes
    axis: YAxis
        The YAxis
    """

    @staticmethod
    def get_yaxis_width(axis: YAxis):
        return get_axis_dim(axis, axis.get_ticks_position())

    @classmethod
    def init_children(cls):
        child_keys = ("Width",)
        child_constraints = (XDistance(),)
        child_prim_keys = (("arg0/Line0/Point0", "arg0/Line0/Point1"),)

        def propogate_child_params(parameters):
            yaxis: YAxis | None
            yaxis, = parameters
            if yaxis is None:
                return [(0,)]
            else:
                return [(cls.get_yaxis_width(yaxis),)]

        return child_keys, child_constraints, child_prim_keys, propogate_child_params

    @classmethod
    def init_aux_data(cls):
        return {
            'RES_ARG_TYPES': (pr.Quadrilateral,),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ('axis',))
        }

# Argument type: tuple[Axes]

# TODO: Handle more specialized x/y axes combos? (i.e. twin x/y axes)
# The below axis constraints are made for single x and y axises

class PositionXAxis(con.CompoundConstruction):
    """
    Constrain the x-axis to the top or bottom of an axes

    Parameters
    ----------
    prims: tuple[pr.Axes]
        The axes
    """

    def __init__(self, bottom: bool=True, top: bool=False):
        return super().__init__(bottom=bottom, top=top)

    @classmethod
    def init_children(cls, bottom: bool, top: bool):

        child_keys = ('CoincidentLines',)
        child_constraints = (CoincidentLines(),)
        if bottom:
            child_prim_keys = (('arg0/Frame/Line0', 'arg0/XAxis/Line2'),)
        elif top:
            child_prim_keys = (('arg0/Frame/Line2', 'arg0/XAxis/Line0'),)
        else:
            raise ValueError(
                "Currently, 'bottom' and 'top' can't both be true"
            )

        def propogate_child_params(params):
            return [(True,)]

        return child_keys, child_constraints, child_prim_keys, propogate_child_params

    @classmethod
    def init_aux_data(cls, bottom: bool, top: bool):
        return {
            'RES_ARG_TYPES': (pr.Axes,),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ())
        }


class PositionYAxis(con.CompoundConstruction):
    """
    Constrain the y-axis to the left or right of an axes

    Parameters
    ----------
    prims: tuple[pr.Axes]
        The axes
    """

    def __init__(self, left: bool=True, right: bool=False):
        return super().__init__(left=left, right=right)

    @classmethod
    def init_children(cls, left: bool=True, right: bool=False):

        child_keys = ('CoincidentLines',)
        child_constraints = (CoincidentLines(),)
        if left:
            child_prim_keys = (('arg0/Frame/Line3', 'arg0/YAxis/Line1'),)
        elif right:
            child_prim_keys = (('arg0/Frame/Line1', 'arg0/YAxis/Line3'),)
        else:
            raise ValueError(
                "Currently, 'left' and 'right' can't both be true"
            )

        def propogate_child_params(params):
            return [(True,)]

        return child_keys, child_constraints, child_prim_keys, propogate_child_params

    @classmethod
    def init_aux_data(cls, left: bool=True, right: bool=False):
        return {
            'RES_ARG_TYPES': (pr.Axes,),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ())
        }


class PositionXAxisLabel(con.CompoundConstruction):
    """
    Constrain the x-axis label horizontal distance (left to right) relative to axes width

    Parameters
    ----------
    prims: tuple[pr.AxesX | pr.Axes]
        The axes
    distance: float
        The axes fraction from the left to position the label
    """

    @classmethod
    def init_children(cls):

        child_keys = ('RelativePointOnLineDistance',)
        child_constraints = (RelativePointOnLineDistance(),)
        child_prim_keys = (('arg0/XAxisLabel', 'arg0/XAxis/Line0'),)

        def propogate_child_params(params):
            distance, = params
            return [(False, distance)]

        return child_keys, child_constraints, child_prim_keys, propogate_child_params

    @classmethod
    def init_aux_data(cls):
        return {
            'RES_ARG_TYPES': (pr.Axes,),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ("distance",))
        }


class PositionYAxisLabel(con.CompoundConstruction):
    """
    Constrain the y-axis label vertical distance (bottom to top) relative to axes height

    Parameters
    ----------
    prims: tuple[pr.AxesX | pr.Axes]
        The axes
    distance: float
        The axes fraction from the bottom to position the label
    """

    @classmethod
    def init_children(cls):
        child_keys = ('RelativePointOnLineDistance',)
        child_constraints = (RelativePointOnLineDistance(),)
        child_prim_keys = (('arg0/YAxisLabel', 'arg0/YAxis/Line1'),)

        def propogate_child_params(params):
            distance, = params
            return [(False, distance)]

        return child_keys, child_constraints, child_prim_keys, propogate_child_params

    @classmethod
    def init_aux_data(cls):
        return {
            'RES_ARG_TYPES': (pr.Axes,),
            'RES_PARAMS_TYPE': namedtuple("Parameters", ("distance",))
        }
