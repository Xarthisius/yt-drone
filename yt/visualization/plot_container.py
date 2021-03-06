"""
A base class for "image" plots with colorbars.



"""

#-----------------------------------------------------------------------------
# Copyright (c) 2013, yt Development Team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file COPYING.txt, distributed with this software.
#-----------------------------------------------------------------------------
import __builtin__
import base64
import numpy as np
import matplotlib
import os
import types
from functools import wraps
from matplotlib.font_manager import FontProperties

from ._mpl_imports import FigureCanvasAgg
from .tick_locators import LogLocator, LinearLocator
from .color_maps import yt_colormaps, is_colormap
from .plot_modifications import \
    callback_registry
from .base_plot_types import CallbackWrapper

from yt.funcs import \
    defaultdict, get_image_suffix, \
    get_ipython_api_version, iterable, \
    ensure_list
from yt.utilities.exceptions import \
    YTNotInsideNotebook


def invalidate_data(f):
    @wraps(f)
    def newfunc(*args, **kwargs):
        rv = f(*args, **kwargs)
        args[0]._data_valid = False
        args[0]._plot_valid = False
        if hasattr(args[0], '_recreate_frb'):
            args[0]._recreate_frb()
        if args[0]._initfinished:
            args[0]._setup_plots()
        return rv
    return newfunc


def invalidate_figure(f):
    @wraps(f)
    def newfunc(*args, **kwargs):
        rv = f(*args, **kwargs)
        for field in args[0].plots.keys():
            args[0].plots[field].figure = None
            args[0].plots[field].axes = None
            args[0].plots[field].cax = None
        return rv
    return newfunc


def invalidate_plot(f):
    @wraps(f)
    def newfunc(*args, **kwargs):
        rv = f(*args, **kwargs)
        args[0]._plot_valid = False
        args[0]._setup_plots()
        return rv
    return newfunc


def apply_callback(f):
    @wraps(f)
    def newfunc(*args, **kwargs):
        #rv = f(*args[1:], **kwargs)
        args[0]._callbacks.append((f.__name__, (args, kwargs)))
        return args[0]
    return newfunc

field_transforms = {}


class FieldTransform(object):
    def __init__(self, name, func, locator):
        self.name = name
        self.func = func
        self.locator = locator
        field_transforms[name] = self

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def ticks(self, mi, ma):
        try:
            ticks = self.locator(mi, ma)
        except:
            ticks = []
        return ticks

log_transform = FieldTransform('log10', np.log10, LogLocator())
linear_transform = FieldTransform('linear', lambda x: x, LinearLocator())

class PlotDictionary(defaultdict):
    def __getitem__(self, item):
        return defaultdict.__getitem__(
            self, self.data_source._determine_fields(item)[0])

    def __setitem__(self, item, value):
        return defaultdict.__setitem__(
            self, self.data_source._determine_fields(item)[0], value)

    def __contains__(self, item):
        return defaultdict.__contains__(
            self, self.data_source._determine_fields(item)[0])

    def __init__(self, data_source, default_factory=None):
        self.data_source = data_source
        return defaultdict.__init__(self, default_factory)

class ImagePlotContainer(object):
    """A countainer for plots with colorbars.

    """
    _plot_type = None
    _plot_valid = False
    _colorbar_valid = False

    def __init__(self, data_source, figure_size, fontsize):
        self.data_source = data_source
        if iterable(figure_size):
            self.figure_size = float(figure_size[0]), float(figure_size[1])
        else:
            self.figure_size = float(figure_size)
        self.plots = PlotDictionary(data_source)
        self._callbacks = []
        self._field_transform = {}
        self._colormaps = defaultdict(lambda: 'algae')
        font_path = matplotlib.get_data_path() + '/fonts/ttf/STIXGeneral.ttf'
        self._font_properties = FontProperties(size=fontsize, fname=font_path)
        self._font_color = None
        self._xlabel = None
        self._ylabel = None
        self._colorbar_label = PlotDictionary(
            self.data_source, lambda: None)

    @invalidate_plot
    def set_log(self, field, log):
        """set a field to log or linear.

        Parameters
        ----------
        field : string
            the field to set a transform
        log : boolean
            Log on/off.

        """
        if field == 'all':
            fields = self.plots.keys()
        else:
            fields = [field]
        for field in self.data_source._determine_fields(fields):
            if log:
                self._field_transform[field] = log_transform
            else:
                self._field_transform[field] = linear_transform
        return self

    def get_log(self, field):
        """get the transform type of a field.

        Parameters
        ----------
        field : string
            the field to get a transform

        """
        log = {}
        if field == 'all':
            fields = self.plots.keys()
        else:
            fields = [field]
        for field in self.data_source._determine_fields(fields):
            if self._field_transform[field] == log_transform:
                log[field] = True
            else:
                log[field] = False
        return log

    @invalidate_plot
    def set_transform(self, field, name):
        field = self.data_source._determine_fields(field)[0]
        if name not in field_transforms:
            raise KeyError(name)
        self._field_transform[field] = field_transforms[name]
        return self

    @invalidate_plot
    def set_cmap(self, field, cmap):
        """set the colormap for one of the fields

        Parameters
        ----------
        field : string
            the field to set the colormap
            if field == 'all', applies to all plots.
        cmap : string or tuple
            If a string, will be interpreted as name of the colormap.
            If a tuple, it is assumed to be of the form (name, type, number)
            to be used for brewer2mpl functionality. (name, type, number, bool)
            can be used to specify if a reverse colormap is to be used.

        """

        if field == 'all':
            fields = self.plots.keys()
        else:
            fields = [field]
        for field in self.data_source._determine_fields(fields):
            self._colorbar_valid = False
            self._colormaps[field] = cmap
        return self

    @invalidate_plot
    def set_zlim(self, field, zmin, zmax, dynamic_range=None):
        """set the scale of the colormap

        Parameters
        ----------
        field : string
            the field to set a colormap scale
            if field == 'all', applies to all plots.
        zmin : float
            the new minimum of the colormap scale. If 'min', will
            set to the minimum value in the current view.
        zmax : float
            the new maximum of the colormap scale. If 'max', will
            set to the maximum value in the current view.

        Other Parameters
        ----------------
        dynamic_range : float (default: None)
            The dynamic range of the image.
            If zmin == None, will set zmin = zmax / dynamic_range
            If zmax == None, will set zmax = zmin * dynamic_range
            When dynamic_range is specified, defaults to setting
            zmin = zmax / dynamic_range.

        """
        if field is 'all':
            fields = self.plots.keys()
        else:
            fields = ensure_list(field)
        for field in self.data_source._determine_fields(fields):
            myzmin = zmin
            myzmax = zmax
            if zmin == 'min':
                myzmin = self.plots[field].image._A.min()
            if zmax == 'max':
                myzmax = self.plots[field].image._A.max()
            if dynamic_range is not None:
                if zmax is None:
                    myzmax = myzmin * dynamic_range
                else:
                    myzmin = myzmax / dynamic_range

            self.plots[field].zmin = myzmin
            self.plots[field].zmax = myzmax
        return self

    def setup_callbacks(self):
        # Left blank to be overriden in subclasses
        pass

    def _setup_plots(self):
        # Left blank to be overriden in subclasses
        pass

    def _switch_ds(self, new_ds, data_source=None):
        old_object = self.data_source
        name = old_object._type_name
        kwargs = dict((n, getattr(old_object, n))
                      for n in old_object._con_args)
        kwargs['center'] = getattr(old_object, 'center', None)
        if data_source is not None:
            if name != "proj":
                raise RuntimeError("The data_source keyword argument "
                                   "is only defined for projections.")
            kwargs['data_source'] = data_source
        new_object = getattr(new_ds, name)(**kwargs)
        self.ds = new_ds
        self.data_source = new_object
        self._data_valid = self._plot_valid = False
        for d in 'xyz':
            lim_name = d+'lim'
            if hasattr(self, lim_name):
                lim = getattr(self, lim_name)
                lim = tuple(new_ds.quan(l.value, str(l.units)) for l in lim)
                setattr(self, lim_name, lim)
        self._recreate_frb()
        self._setup_plots()

    def __getitem__(self, item):
        return self.plots[item]

    def run_callbacks(self, f):
        keys = self.frb.keys()
        for name, (args, kwargs) in self._callbacks:
            cbw = CallbackWrapper(self, self.plots[f], self.frb, f)
            CallbackMaker = callback_registry[name]
            callback = CallbackMaker(*args[1:], **kwargs)
            callback(cbw)
        for key in self.frb.keys():
            if key not in keys:
                del self.frb[key]

    @invalidate_plot
    @invalidate_figure
    def set_font(self, font_dict=None):
        """set the font and font properties

        Parameters
        ----------
        font_dict : dict
        A dict of keyword parameters to be passed to
        :py:class:`matplotlib.font_manager.FontProperties`.

        Possible keys include
        * family - The font family. Can be serif, sans-serif, cursive, 'fantasy' or
          'monospace'.
        * style - The font style. Either normal, italic or oblique.
        * color - A valid color string like 'r', 'g', 'red', 'cobalt', and
          'orange'.
        * variant: Either normal or small-caps.
        * size: Either an relative value of xx-small, x-small, small, medium,
          large, x-large, xx-large or an absolute font size, e.g. 12
        * stretch: A numeric value in the range 0-1000 or one of
          ultra-condensed, extra-condensed, condensed, semi-condensed, normal,
          semi-expanded, expanded, extra-expanded or ultra-expanded
        * weight: A numeric value in the range 0-1000 or one of ultralight,
          light, normal, regular, book, medium, roman, semibold, demibold, demi,
          bold, heavy, extra bold, or black

        See the matplotlib font manager API documentation for more details.
        http://matplotlib.org/api/font_manager_api.html

        Notes
        -----
        Mathtext axis labels will only obey the `size` and `color` keyword.

        Examples
        --------
        This sets the font to be 24-pt, blue, sans-serif, italic, and
        bold-face.

        >>> slc = SlicePlot(ds, 'x', 'Density')
        >>> slc.set_font({'family':'sans-serif', 'style':'italic',
                          'weight':'bold', 'size':24, 'color':'blue'})

        """
        if font_dict is None:
            font_dict = {}
        if 'color' in font_dict:
            self._font_color = font_dict.pop('color')
        # Set default values if the user does not explicitly set them.
        # this prevents reverting to the matplotlib defaults.
        font_dict.setdefault('family', 'stixgeneral')
        font_dict.setdefault('size', 18)
        self._font_properties = \
            FontProperties(**font_dict)
        return self

    def set_font_size(self, size):
        """Set the size of the font used in the plot

        This sets the font size by calling the set_font function.  See set_font
        for more font customization options.

        Parameters
        ----------
        size : float
        The absolute size of the font in points (1 pt = 1/72 inch).

        """
        return self.set_font({'size': size})

    @invalidate_plot
    @invalidate_figure
    def set_figure_size(self, size):
        """Sets a new figure size for the plot

        parameters
        ----------
        size : float
            The size of the figure on the longest axis (in units of inches),
            including the margins but not the colorbar.
        """
        self.figure_size = float(size)
        return self

    def save(self, name=None, mpl_kwargs=None):
        """saves the plot to disk.

        Parameters
        ----------
        name : string
           The base of the filename.  If name is a directory or if name is not
           set, the filename of the dataset is used.
        mpl_kwargs : dict
           A dict of keyword arguments to be passed to matplotlib.

        >>> slc.save(mpl_kwargs={'bbox_inches':'tight'})

        """
        names = []
        if mpl_kwargs is None: mpl_kwargs = {}
        if name is None:
            name = str(self.ds)
        name = os.path.expanduser(name)
        if name[-1] == os.sep and not os.path.isdir(name):
            os.mkdir(name)
        if os.path.isdir(name) and name != str(self.ds):
            name = name + (os.sep if name[-1] != os.sep else '') + str(self.ds)
        suffix = get_image_suffix(name)
        if suffix != '':
            for k, v in self.plots.iteritems():
                names.append(v.save(name, mpl_kwargs))
            return names
        axis = self.ds.coordinates.axis_name.get(
            self.data_source.axis, '')
        weight = None
        type = self._plot_type
        if type in ['Projection', 'OffAxisProjection']:
            weight = self.data_source.weight_field
            if weight is not None:
                weight = weight[1].replace(' ', '_')
        if 'Cutting' in self.data_source.__class__.__name__:
            type = 'OffAxisSlice'
        for k, v in self.plots.iteritems():
            if isinstance(k, types.TupleType):
                k = k[1]
            if axis:
                n = "%s_%s_%s_%s" % (name, type, axis, k.replace(' ', '_'))
            else:
                # for cutting planes
                n = "%s_%s_%s" % (name, type, k.replace(' ', '_'))
            if weight:
                n += "_%s" % (weight)
            names.append(v.save(n, mpl_kwargs))
        return names

    @invalidate_data
    def refresh(self):
        # invalidate_data will take care of everything
        return self

    def _send_zmq(self):
        try:
            # pre-IPython v1.0
            from IPython.zmq.pylab.backend_inline import send_figure as display
        except ImportError:
            # IPython v1.0+
            from IPython.core.display import display
        for k, v in sorted(self.plots.iteritems()):
            # Due to a quirk in the matplotlib API, we need to create
            # a dummy canvas variable here that is never used.
            canvas = FigureCanvasAgg(v.figure)  # NOQA
            display(v.figure)

    def show(self):
        r"""This will send any existing plots to the IPython notebook.
        function name.

        If yt is being run from within an IPython session, and it is able to
        determine this, this function will send any existing plots to the
        notebook for display.

        If yt can't determine if it's inside an IPython session, it will raise
        YTNotInsideNotebook.

        Examples
        --------

        >>> from yt.mods import SlicePlot
        >>> slc = SlicePlot(ds, "x", ["Density", "VelocityMagnitude"])
        >>> slc.show()

        """
        if "__IPYTHON__" in dir(__builtin__):
            api_version = get_ipython_api_version()
            if api_version in ('0.10', '0.11'):
                self._send_zmq()
            else:
                from IPython.display import display
                display(self)
        else:
            raise YTNotInsideNotebook

    def display(self, name=None, mpl_kwargs=None):
        """Will attempt to show the plot in in an IPython notebook.
        Failing that, the plot will be saved to disk."""
        try:
            return self.show()
        except YTNotInsideNotebook:
            return self.save(name=name, mpl_kwargs=mpl_kwargs)

    def _repr_html_(self):
        """Return an html representation of the plot object. Will display as a
        png for each WindowPlotMPL instance in self.plots"""
        ret = ''
        for field in self.plots:
            img = base64.b64encode(self.plots[field]._repr_png_())
            ret += '<img src="data:image/png;base64,%s"><br>' % img
        return ret

    @invalidate_plot
    def set_xlabel(self, label):
        r"""
        Allow the user to modify the X-axis title
        Defaults to the global value. Fontsize defaults
        to 18.

        Parameters
        ----------
        x_title: str
              The new string for the x-axis.

        >>>  plot.set_xtitle("H2I Number Density (cm$^{-3}$)")

        """
        self._xlabel = label
        return self

    @invalidate_plot
    def set_ylabel(self, label):
        r"""
        Allow the user to modify the Y-axis title
        Defaults to the global value.

        Parameters
        ----------
        label: str
          The new string for the y-axis.

        >>>  plot.set_ytitle("Temperature (K)")

        """
        self._ylabel = label
        return self

    @invalidate_plot
    def set_colorbar_label(self, field, label):
        r"""
        Sets the colorbar label.

        Parameters
        ----------
        field: str or tuple
          The name of the field to modify the label for.
        label: str
          The new label

        >>>  plot.set_colorbar_label("Enclosed Gas Mass ($M_{\odot}$)")

        """
        self._colorbar_label[field] = label
        return self

    def _get_axes_labels(self, field):
        return(self._xlabel, self._ylabel, self._colorbar_label[field])
