"""
Orion data-file handling functions



"""

#-----------------------------------------------------------------------------
# Copyright (c) 2013, yt Development Team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file COPYING.txt, distributed with this software.
#-----------------------------------------------------------------------------

import os
import numpy as np
from yt.utilities.lib.fortran_reader import \
    read_castro_particles, \
    read_and_seek
from yt.utilities.io_handler import \
           BaseIOHandler
from yt.funcs import mylog, defaultdict

class IOHandlerBoxlib(BaseIOHandler):

    _dataset_type = "boxlib_native"

    def __init__(self, ds, *args, **kwargs):
        self.ds = ds

    def _read_fluid_selection(self, chunks, selector, fields, size):
        chunks = list(chunks)
        if any((ftype != "boxlib" for ftype, fname in fields)):
            raise NotImplementedError
        rv = {}
        for field in fields:
            rv[field] = np.empty(size, dtype="float64")
        ng = sum(len(c.objs) for c in chunks)
        mylog.debug("Reading %s cells of %s fields in %s grids",
                    size, [f2 for f1, f2 in fields], ng)
        ind = 0
        for chunk in chunks:
            data = self._read_chunk_data(chunk, fields)
            for g in chunk.objs:
                for field in fields:
                    ds = data[g.id].pop(field)
                    nd = g.select(selector, ds, rv[field], ind) # caches
                ind += nd
                data.pop(g.id)
        return rv

    def _read_chunk_data(self, chunk, fields):
        data = {}
        grids_by_file = defaultdict(list)
        if len(chunk.objs) == 0: return data
        for g in chunk.objs:
            if g.filename is None:
                continue
            grids_by_file[g.filename].append(g)
        dtype = self.ds.index._dtype
        bpr = dtype.itemsize
        for filename in grids_by_file:
            grids = grids_by_file[filename]
            grids.sort(key = lambda a: a._offset)
            f = open(filename, "rb")
            for grid in grids:
                data[grid.id] = {}
                grid._seek(f)
                count = grid.ActiveDimensions.prod()
                size = count * bpr
                for field in self.ds.index.field_order:
                    if field in fields:
                        # We read it ...
                        v = np.fromfile(f, dtype=dtype, count=count)
                        v = v.reshape(grid.ActiveDimensions, order='F')
                        data[grid.id][field] = v
                    else:
                        f.seek(size, os.SEEK_CUR)
        return data

class IOHandlerOrion(IOHandlerBoxlib):
    _dataset_type = "orion_native"

    def _read_particles(self, grid, field): 
        """
        parses the Orion Star Particle text files
        
        """

        fn = grid.ds.fullplotdir + "/StarParticles"
        if not os.path.exists(fn):
            fn = grid.ds.fullplotdir + "/SinkParticles"

        # Figure out the format of the particle file
        with open(fn, 'r') as f:
            lines = f.readlines()
        line = lines[1]
        
        # The basic fields that all sink particles have
        index = {'particle_mass': 0,
                 'particle_position_x': 1,
                 'particle_position_y': 2,
                 'particle_position_z': 3,
                 'particle_momentum_x': 4,
                 'particle_momentum_y': 5,
                 'particle_momentum_z': 6,
                 'particle_angmomen_x': 7,
                 'particle_angmomen_y': 8,
                 'particle_angmomen_z': 9,
                 'particle_mlast': 10,
                 'particle_mdeut': 11,
                 'particle_n': 12,
                 'particle_mdot': 13,
                 'particle_burnstate': 14,
                 'particle_id': 15}

        if len(line.strip().split()) == 11:
            # these are vanilla sinks, do nothing
            pass  

        elif len(line.strip().split()) == 17:
            # these are old-style stars, add stellar model parameters
            index['particle_mlast']     = 10
            index['particle_r']         = 11
            index['particle_mdeut']     = 12
            index['particle_n']         = 13
            index['particle_mdot']      = 14,
            index['particle_burnstate'] = 15

        elif len(line.strip().split()) == 18:
            # these are the newer style, add luminosity as well
            index['particle_mlast']     = 10
            index['particle_r']         = 11
            index['particle_mdeut']     = 12
            index['particle_n']         = 13
            index['particle_mdot']      = 14,
            index['particle_burnstate'] = 15,
            index['particle_luminosity']= 16

        else:
            # give a warning if none of the above apply:
            mylog.warning('Warning - could not figure out particle output file')
            mylog.warning('These results could be nonsense!')

        def read(line, field):
            return float(line.strip().split(' ')[index[field]])

        with open(fn, 'r') as f:
            lines = f.readlines()
            particles = []
            for line in lines[1:]:
                if grid.NumberOfParticles > 0:
                    coord = read(line, "particle_position_x"), \
                            read(line, "particle_position_y"), \
                            read(line, "particle_position_z") 
                    if ( (grid.LeftEdge < coord).all() and 
                         (coord <= grid.RightEdge).all() ):
                        particles.append(read(line, field))
        return np.array(particles)

class IOHandlerCastro(IOHandlerBoxlib):
    _dataset_type = "castro_native"

    def _read_particle_field(self, grid, field):
        offset = grid._particle_offset
        filen = os.path.expanduser(grid.particle_filename)
        off = grid._particle_offset
        tr = np.zeros(grid.NumberOfParticles, dtype='float64')
        read_castro_particles(filen, off,
            castro_particle_field_names.index(field),
            len(castro_particle_field_names),
            tr)
        return tr

nyx_particle_field_names = ['particle_position_%s' % ax for ax in 'xyz'] + \
                           ['particle_mass'] +  \
                           ['particle_velocity_%s' % ax for ax in 'xyz']

class IOHandlerNyx(IOHandlerBoxlib):
    _dataset_type = "nyx_native"

    def _read_particle_coords(self, chunks, ptf):
        offset = grid._particle_offset
        filen = os.path.expanduser(grid.particle_filename)
        off = grid._particle_offset
        tr = np.zeros(grid.NumberOfParticles, dtype='float64')
        read_castro_particles(filen, off,
                            nyx_particle_field_names.index(field),
                            len(nyx_particle_field_names), tr)

    def _read_particle_fields(self, chunks, ptf, fields):
        pass
