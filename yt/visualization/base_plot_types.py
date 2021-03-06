"""
This is a place for base classes of the various plot types.



"""

#-----------------------------------------------------------------------------
# Copyright (c) 2013, yt Development Team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file COPYING.txt, distributed with this software.
#-----------------------------------------------------------------------------
import matplotlib
from yt.extern.six.moves import StringIO
from ._mpl_imports import \
    FigureCanvasAgg, FigureCanvasPdf, FigureCanvasPS
from yt.funcs import \
    get_image_suffix, mylog, iterable
import numpy as np
try:
    import brewer2mpl
    has_brewer = True
except:
    has_brewer = False


class CallbackWrapper(object):
    def __init__(self, viewer, window_plot, frb, field):
        self.frb = frb
        self.data = frb.data_source
        self._axes = window_plot.axes
        self._figure = window_plot.figure
        if len(self._axes.images) > 0:
            self.image = self._axes.images[0]
        if frb.axis < 3:
            DD = frb.ds.domain_width
            xax = frb.ds.coordinates.x_axis[frb.axis]
            yax = frb.ds.coordinates.y_axis[frb.axis]
            self._period = (DD[xax], DD[yax])
        self.ds = frb.ds
        self.xlim = viewer.xlim
        self.ylim = viewer.ylim
        if 'OffAxisSlice' in viewer._plot_type:
            self._type_name = "CuttingPlane"
        else:
            self._type_name = viewer._plot_type


class PlotMPL(object):
    """A base class for all yt plots made using matplotlib.

    """
    def __init__(self, fsize, axrect, figure, axes):
        """Initialize PlotMPL class"""
        self._plot_valid = True
        if figure is None:
            self.figure = matplotlib.figure.Figure(figsize=fsize, frameon=True)
        else:
            figure.set_size_inches(fsize)
            self.figure = figure
        if axes is None:
            self.axes = self.figure.add_axes(axrect)
        else:
            axes.cla()
            axes.set_position(axrect)
            self.axes = axes
        self.canvas = FigureCanvasAgg(self.figure)

    def save(self, name, mpl_kwargs=None, canvas=None):
        """Choose backend and save image to disk"""
        if mpl_kwargs is None:
            mpl_kwargs = {}

        suffix = get_image_suffix(name)
        if suffix == '':
            suffix = '.png'
            name = "%s%s" % (name, suffix)

        mylog.info("Saving plot %s", name)

        if suffix == ".png":
            canvas = FigureCanvasAgg(self.figure)
        elif suffix == ".pdf":
            canvas = FigureCanvasPdf(self.figure)
        elif suffix in (".eps", ".ps"):
            canvas = FigureCanvasPS(self.figure)
        else:
            mylog.warning("Unknown suffix %s, defaulting to Agg", suffix)
            canvas = self.canvas

        canvas.print_figure(name, **mpl_kwargs)
        return name


class ImagePlotMPL(PlotMPL):
    """A base class for yt plots made using imshow

    """
    def __init__(self, fsize, axrect, caxrect, zlim, figure, axes, cax):
        """Initialize ImagePlotMPL class object"""
        super(ImagePlotMPL, self).__init__(fsize, axrect, figure, axes)
        self.zmin, self.zmax = zlim
        if cax is None:
            self.cax = self.figure.add_axes(caxrect)
        else:
            cax.cla()
            cax.set_position(caxrect)
            self.cax = cax

    def _init_image(self, data, cbnorm, cmap, extent, aspect):
        """Store output of imshow in image variable"""
        if (cbnorm == 'log10'):
            norm = matplotlib.colors.LogNorm()
        elif (cbnorm == 'linear'):
            norm = matplotlib.colors.Normalize()
        extent = [float(e) for e in extent]
        if isinstance(cmap, tuple):
            if has_brewer:
                bmap = brewer2mpl.get_map(*cmap)
                cmap = bmap.get_mpl_colormap(N=cmap[2])
            else:
                raise RuntimeError("Please install brewer2mpl to use colorbrewer colormaps")

        self.image = self.axes.imshow(data.to_ndarray(), origin='lower',
                                      extent=extent, norm=norm, vmin=self.zmin,
                                      aspect=aspect, vmax=self.zmax, cmap=cmap)
        self.cb = self.figure.colorbar(self.image, self.cax)

    def _repr_png_(self):
        canvas = FigureCanvasAgg(self.figure)
        f = StringIO()
        canvas.print_figure(f)
        f.seek(0)
        return f.read()

    def _get_best_layout(self):
        if self._draw_colorbar:
            cb_size = self._cb_size
            cb_text_size = self._ax_text_size[1] + 0.45
        else:
            cb_size = 0.0
            cb_text_size = 0.0

        if self._draw_axes:
            x_axis_size = self._ax_text_size[0]
            y_axis_size = self._ax_text_size[1]
        else:
            x_axis_size = 0.0
            y_axis_size = 0.0

        if self._draw_axes or self._draw_colorbar:
            top_buff_size = self._top_buff_size
        else:
            top_buff_size = 0.0

        # Ensure the figure size along the long axis is always equal to _figure_size
        if iterable(self._figure_size):
            x_fig_size = self._figure_size[0]
            y_fig_size = self._figure_size[1]
        else:
            if self._aspect >= 1.0:
                x_fig_size = self._figure_size
                y_fig_size = self._figure_size/self._aspect
            if self._aspect < 1.0:
                x_fig_size = self._figure_size*self._aspect
                y_fig_size = self._figure_size

        xbins = np.array([x_axis_size, x_fig_size, cb_size, cb_text_size])
        ybins = np.array([y_axis_size, y_fig_size, top_buff_size])

        size = [xbins.sum(), ybins.sum()]

        x_frac_widths = xbins/size[0]
        y_frac_widths = ybins/size[1]

        axrect = (
            x_frac_widths[0],
            y_frac_widths[0],
            x_frac_widths[1],
            y_frac_widths[1],
        )

        caxrect = (
            x_frac_widths[0]+x_frac_widths[1],
            y_frac_widths[0],
            x_frac_widths[2],
            y_frac_widths[1],
        )

        return size, axrect, caxrect

    def _toggle_axes(self, choice):
        self._draw_axes = choice
        self.axes.get_xaxis().set_visible(choice)
        self.axes.get_yaxis().set_visible(choice)
        self.axes.set_frame_on(choice)
        size, axrect, caxrect = self._get_best_layout()
        self.axes.set_position(axrect)
        self.cax.set_position(caxrect)
        self.figure.set_size_inches(*size)

    def _toggle_colorbar(self, choice):
        self._draw_colorbar = choice
        self.cax.set_visible(choice)
        size, axrect, caxrect = self._get_best_layout()
        self.axes.set_position(axrect)
        self.cax.set_position(caxrect)
        self.figure.set_size_inches(*size)

    def hide_axes(self):
        self._toggle_axes(False)
        return self

    def show_axes(self):
        self._toggle_axes(True)
        return self

    def hide_colorbar(self):
        self._toggle_colorbar(False)
        return self

    def show_colorbar(self):
        self._toggle_colorbar(True)
        return self

def get_multi_plot(nx, ny, colorbar = 'vertical', bw = 4, dpi=300,
                   cbar_padding = 0.4):
    r"""Construct a multiple axes plot object, with or without a colorbar, into
    which multiple plots may be inserted.

    This will create a set of :class:`matplotlib.axes.Axes`, all lined up into
    a grid, which are then returned to the user and which can be used to plot
    multiple plots on a single figure.

    Parameters
    ----------
    nx : int
        Number of axes to create along the x-direction
    ny : int
        Number of axes to create along the y-direction
    colorbar : {'vertical', 'horizontal', None}, optional
        Should Axes objects for colorbars be allocated, and if so, should they
        correspond to the horizontal or vertical set of axes?
    bw : number
        The base height/width of an axes object inside the figure, in inches
    dpi : number
        The dots per inch fed into the Figure instantiation

    Returns
    -------
    fig : :class:`matplotlib.figure.Figure`
        The figure created inside which the axes reside
    tr : list of list of :class:`matplotlib.axes.Axes` objects
        This is a list, where the inner list is along the x-axis and the outer
        is along the y-axis
    cbars : list of :class:`matplotlib.axes.Axes` objects
        Each of these is an axes onto which a colorbar can be placed.

    Notes
    -----
    This is a simple implementation for a common use case.  Viewing the source
    can be instructure, and is encouraged to see how to generate more
    complicated or more specific sets of multiplots for your own purposes.
    """
    hf, wf = 1.0/ny, 1.0/nx
    fudge_x = fudge_y = 1.0
    if colorbar is None:
        fudge_x = fudge_y = 1.0
    elif colorbar.lower() == 'vertical':
        fudge_x = nx/(cbar_padding+nx)
        fudge_y = 1.0
    elif colorbar.lower() == 'horizontal':
        fudge_x = 1.0
        fudge_y = ny/(cbar_padding+ny)
    fig = matplotlib.figure.Figure((bw*nx/fudge_x, bw*ny/fudge_y), dpi=dpi)
    from _mpl_imports import FigureCanvasAgg
    fig.set_canvas(FigureCanvasAgg(fig))
    fig.subplots_adjust(wspace=0.0, hspace=0.0,
                        top=1.0, bottom=0.0,
                        left=0.0, right=1.0)
    tr = []
    for j in range(ny):
        tr.append([])
        for i in range(nx):
            left = i*wf*fudge_x
            bottom = fudge_y*(1.0-(j+1)*hf) + (1.0-fudge_y)
            ax = fig.add_axes([left, bottom, wf*fudge_x, hf*fudge_y])
            tr[-1].append(ax)
    cbars = []
    if colorbar is None:
        pass
    elif colorbar.lower() == 'horizontal':
        for i in range(nx):
            # left, bottom, width, height
            # Here we want 0.10 on each side of the colorbar
            # We want it to be 0.05 tall
            # And we want a buffer of 0.15
            ax = fig.add_axes([wf*(i+0.10)*fudge_x, hf*fudge_y*0.20,
                               wf*(1-0.20)*fudge_x, hf*fudge_y*0.05])
            cbars.append(ax)
    elif colorbar.lower() == 'vertical':
        for j in range(ny):
            ax = fig.add_axes([wf*(nx+0.05)*fudge_x, hf*fudge_y*(ny-(j+0.95)),
                               wf*fudge_x*0.05, hf*fudge_y*0.90])
            ax.clear()
            cbars.append(ax)
    return fig, tr, cbars
