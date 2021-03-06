"""
OWLS-specific fields




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
import owls_ion_tables as oit

from yt.funcs import *

from yt.fields.field_info_container import \
    FieldInfoContainer

from .definitions import \
    gadget_ptypes, \
    ghdf5_ptypes,\
    eaglenetwork_ion_lookup

from yt.units.yt_array import YTQuantity
from yt.config import ytcfg
from yt.utilities.physical_constants import mh
from yt.utilities.periodic_table import periodic_table
from yt.fields.species_fields import \
    add_species_field_by_fraction, \
    add_species_field_by_density, \
    setup_species_fields

from yt.fields.particle_fields import \
    add_volume_weighted_smoothed_field


# Here are helper functions for things like vector fields and so on.

def _get_conv(cf):
    def _convert(data):
        return data.convert(cf)
    return _convert

class SPHFieldInfo(FieldInfoContainer):
    known_other_fields = ()

    known_particle_fields = (
        ("Mass", ("code_mass", ["particle_mass"], None)),
        ("Masses", ("code_mass", ["particle_mass"], None)),
        ("Coordinates", ("code_length", ["particle_position"], None)),
        ("Velocity", ("code_velocity", ["particle_velocity"], None)),
        ("Velocities", ("code_velocity", ["particle_velocity"], None)),
        ("ParticleIDs", ("", ["particle_index"], None)),
        ("InternalEnergy", ("", ["thermal_energy"], None)),
        ("SmoothingLength", ("code_length", ["smoothing_length"], None)),
        ("Density", ("code_mass / code_length**3", ["density"], None)),
        ("MaximumTemperature", ("K", [], None)),
        ("Temperature", ("K", ["temperature"], None)),
        ("Epsilon", ("code_length", [], None)),
        ("Metals", ("code_metallicity", ["metallicity"], None)),
        ("Metallicity", ("code_metallicity", ["metallicity"], None)),
        ("Phi", ("code_length", [], None)),
        ("FormationTime", ("code_time", ["creation_time"], None)),
        # These are metallicity fields that get discovered for FIRE simulations
        ("Metallicity_00", ("", ["metallicity"], None)),
        ("Metallicity_01", ("", ["He_fraction"], None)),
        ("Metallicity_02", ("", ["C_fraction"], None)),
        ("Metallicity_03", ("", ["N_fraction"], None)),
        ("Metallicity_04", ("", ["O_fraction"], None)),
        ("Metallicity_05", ("", ["Ne_fraction"], None)),
        ("Metallicity_06", ("", ["Mg_fraction"], None)),
        ("Metallicity_07", ("", ["Si_fraction"], None)),
        ("Metallicity_08", ("", ["S_fraction"], None)),
        ("Metallicity_09", ("", ["Ca_fraction"], None)),
        ("Metallicity_10", ("", ["Fe_fraction"], None)),
    )

    def __init__(self, *args, **kwargs):
        super(SPHFieldInfo, self).__init__(*args, **kwargs)
        # Special case for FIRE
        if ("PartType0", "Metallicity_00") in self.field_list:
            self.species_names += ["He", "C", "N", "O", "Ne", "Mg", "Si", "S",
                "Ca", "Fe"]

    def setup_particle_fields(self, ptype, *args, **kwargs):
        super(SPHFieldInfo, self).setup_particle_fields(ptype, *args, **kwargs)
        setup_species_fields(self, ptype)

class TipsyFieldInfo(SPHFieldInfo):
    aux_particle_fields = {
        'uDotFB':("uDotFB", ("code_mass * code_velocity**2", ["uDotFB"], None)),
        'uDotAV':("uDotAV", ("code_mass * code_velocity**2", ["uDotAV"], None)),
        'uDotPdV':("uDotPdV", ("code_mass * code_velocity**2", ["uDotPdV"], None)),
        'uDotHydro':("uDotHydro", ("code_mass * code_velocity**2", ["uDotHydro"], None)),
        'uDotDiff':("uDotDiff", ("code_mass * code_velocity**2", ["uDotDiff"], None)),
        'uDot':("uDot", ("code_mass * code_velocity**2", ["uDot"], None)),
        'coolontime':("coolontime", ("code_time", ["coolontime"], None)),
        'timeform':("timeform", ("code_time", ["timeform"], None)),
        'massform':("massform", ("code_mass", ["massform"], None)),
        'HI':("HI", ("dimensionless", ["HI"], None)),
        'HII':("HII", ("dimensionless", ["HII"], None)),
        'HeI':("HeI", ("dimensionless", ["HeI"], None)),
        'HeII':("HeII", ("dimensionless", ["HeII"], None)),
        'OxMassFrac':("OxMassFrac", ("dimensionless", ["OxMassFrac"], None)),
        'FeMassFrac':("FeMassFrac", ("dimensionless", ["FeMassFrac"], None)),
        'c':("c", ("code_velocity", ["c"], None)),
        'acc':("acc", ("code_velocity / code_time", ["acc"], None)),
        'accg':("accg", ("code_velocity / code_time", ["accg"], None))}
    
    def __init__(self, ds, field_list, slice_info = None):
        for field in field_list:
            if field[1] in self.aux_particle_fields.keys() and \
                self.aux_particle_fields[field[1]] not in self.known_particle_fields:
                self.known_particle_fields += (self.aux_particle_fields[field[1]],)
        super(TipsyFieldInfo,self).__init__(ds, field_list, slice_info)


        

class OWLSFieldInfo(SPHFieldInfo):

    _ions = ("c1", "c2", "c3", "c4", "c5", "c6",
             "fe2", "fe17", "h1", "he1", "he2", "mg1", "mg2", "n2", 
             "n3", "n4", "n5", "n6", "n7", "ne8", "ne9", "ne10", "o1", 
             "o6", "o7", "o8", "si2", "si3", "si4", "si13")

    _elements = ("H", "He", "C", "N", "O", "Ne", "Mg", "Si", "Fe")

    _num_neighbors = 48

    _add_elements = ("PartType0", "PartType4")

    _add_ions = ("PartType0")


    def __init__(self, *args, **kwargs):
        
        new_particle_fields = (
            ("Hydrogen", ("", ["H_fraction"], None)),
            ("Helium", ("", ["He_fraction"], None)),
            ("Carbon", ("", ["C_fraction"], None)),
            ("Nitrogen", ("", ["N_fraction"], None)),
            ("Oxygen", ("", ["O_fraction"], None)),
            ("Neon", ("", ["Ne_fraction"], None)),
            ("Magnesium", ("", ["Mg_fraction"], None)),
            ("Silicon", ("", ["Si_fraction"], None)),
            ("Iron", ("", ["Fe_fraction"], None))
            )

        self.known_particle_fields += new_particle_fields
        
        super(OWLSFieldInfo,self).__init__( *args, **kwargs )



    def setup_particle_fields(self, ptype):
        """ additional particle fields derived from those in snapshot.
        we also need to add the smoothed fields here b/c setup_fluid_fields
        is called before setup_particle_fields. """ 

        smoothed_suffixes = ("_number_density", "_density", "_mass")



        # we add particle element fields for stars and gas
        #-----------------------------------------------------
        if ptype in self._add_elements:


            # this adds the particle element fields
            # X_density, X_mass, and X_number_density
            # where X is an item of self._elements.
            # X_fraction are defined in snapshot
            #-----------------------------------------------
            for s in self._elements:
                add_species_field_by_fraction(self, ptype, s,
                                              particle_type=True)

        # this needs to be called after the call to 
        # add_species_field_by_fraction for some reason ...
        # not sure why yet. 
        #-------------------------------------------------------
        if ptype == 'PartType0':
            ftype='gas'
        elif ptype == 'PartType1':
            ftype='dm'
        elif ptype == 'PartType2':
            ftype='PartType2'
        elif ptype == 'PartType3':
            ftype='PartType3'
        elif ptype == 'PartType4':
            ftype='star'
        elif ptype == 'PartType5':
            ftype='BH'
        elif ptype == 'all':
            ftype='all'
        
        super(OWLSFieldInfo,self).setup_particle_fields(
            ptype, num_neighbors=self._num_neighbors, ftype=ftype)


        # and now we add the smoothed versions for PartType0
        #-----------------------------------------------------
        if ptype == 'PartType0':

            loaded = []
            for s in self._elements:
                for sfx in smoothed_suffixes:
                    fname = s + sfx
                    fn = add_volume_weighted_smoothed_field( 
                        ptype, "particle_position", "particle_mass",
                        "smoothing_length", "density", fname, self,
                        self._num_neighbors)
                    loaded += fn

                    self.alias(("gas", fname), fn[0])

            self._show_field_errors += loaded
            self.find_dependencies(loaded)


            # we only add ion fields for gas.  this takes some 
            # time as the ion abundances have to be interpolated
            # from cloudy tables (optically thin)
            #-----------------------------------------------------
    

            # this defines the ion density on particles
            # X_density for all items in self._ions
            #-----------------------------------------------
            self.setup_gas_ion_density_particle_fields( ptype )

            # this adds the rest of the ion particle fields
            # X_fraction, X_mass, X_number_density
            #-----------------------------------------------
            for ion in self._ions:

                # construct yt name for ion
                #---------------------------------------------------
                if ion[0:2].isalpha():
                    symbol = ion[0:2].capitalize()
                    roman = int(ion[2:])
                else:
                    symbol = ion[0:1].capitalize()
                    roman = int(ion[1:])

                pstr = "_p" + str(roman-1)
                yt_ion = symbol + pstr

                # add particle field
                #---------------------------------------------------
                add_species_field_by_density(self, ptype, yt_ion,
                                             particle_type=True)


            # add smoothed ion fields
            #-----------------------------------------------
            for ion in self._ions:

                # construct yt name for ion
                #---------------------------------------------------
                if ion[0:2].isalpha():
                    symbol = ion[0:2].capitalize()
                    roman = int(ion[2:])
                else:
                    symbol = ion[0:1].capitalize()
                    roman = int(ion[1:])

                pstr = "_p" + str(roman-1)
                yt_ion = symbol + pstr

                loaded = []
                for sfx in smoothed_suffixes:
                    fname = yt_ion + sfx
                    fn = add_volume_weighted_smoothed_field( 
                        ptype, "particle_position", "particle_mass",
                        "smoothing_length", "density", fname, self,
                        self._num_neighbors)
                    loaded += fn

                    self.alias(("gas", fname), fn[0])

                self._show_field_errors += loaded
                self.find_dependencies(loaded)



    def setup_gas_ion_density_particle_fields( self, ptype ):
        """ Sets up particle fields for gas ion densities. """ 

        # loop over all ions and make fields
        #----------------------------------------------
        for ion in self._ions:

            # construct yt name for ion
            #---------------------------------------------------
            if ion[0:2].isalpha():
                symbol = ion[0:2].capitalize()
                roman = int(ion[2:])
            else:
                symbol = ion[0:1].capitalize()
                roman = int(ion[1:])

            pstr = "_p" + str(roman-1)
            yt_ion = symbol + pstr
            ftype = ptype

            # add ion density field for particles
            #---------------------------------------------------
            fname = yt_ion + '_density'
            dens_func = self._create_ion_density_func( ftype, ion )
            self.add_field( (ftype, fname),
                            function = dens_func, 
                            units="g/cm**3",
                            particle_type=True )            
            self._show_field_errors.append( (ftype,fname) )



        
    def _create_ion_density_func( self, ftype, ion ):
        """ returns a function that calculates the ion density of a particle. 
        """ 

        def _ion_density(field, data):

            # get element symbol from ion string. ion string will 
            # be a member of the tuple _ions (i.e. si13)
            #--------------------------------------------------------
            if ion[0:2].isalpha():
                symbol = ion[0:2].capitalize()
            else:
                symbol = ion[0:1].capitalize()

            # mass fraction for the element
            #--------------------------------------------------------
            m_frac = data[ftype, symbol+"_fraction"]

            # get nH and T for lookup
            #--------------------------------------------------------
            log_nH = np.log10( data["PartType0", "H_number_density"] )
            log_T = np.log10( data["PartType0", "Temperature"] )

            # get name of owls_ion_file for given ion
            #--------------------------------------------------------
            owls_ion_path = self._get_owls_ion_data_dir()
            fname = os.path.join( owls_ion_path, ion+".hdf5" )

            # create ionization table for this redshift
            #--------------------------------------------------------
            itab = oit.IonTableOWLS( fname )
            itab.set_iz( data.ds.current_redshift )

            # find ion balance using log nH and log T
            #--------------------------------------------------------
            i_frac = itab.interp( log_nH, log_T )
            return data[ftype,"Density"] * m_frac * i_frac 
        
        return _ion_density





    # this function sets up the X_mass, X_density, X_fraction, and
    # X_number_density fields where X is the name of an OWLS element.
    #-------------------------------------------------------------
    def setup_fluid_fields(self):

        return



    # this function returns the owls_ion_data directory. if it doesn't
    # exist it will download the data from http://yt-project.org/data
    #-------------------------------------------------------------
    def _get_owls_ion_data_dir(self):

        txt = "Attempting to download ~ 30 Mb of owls ion data from %s to %s."
        data_file = "owls_ion_data.tar.gz"
        data_url = "http://yt-project.org/data"

        # get test_data_dir from yt config (ytcgf)
        #----------------------------------------------
        tdir = ytcfg.get("yt","test_data_dir")

        # set download destination to tdir or ./ if tdir isnt defined
        #----------------------------------------------
        if tdir == "/does/not/exist":
            data_dir = "./"
        else:
            data_dir = tdir            


        # check for owls_ion_data directory in data_dir
        # if not there download the tarball and untar it
        #----------------------------------------------
        owls_ion_path = os.path.join( data_dir, "owls_ion_data" )

        if not os.path.exists(owls_ion_path):
            mylog.info(txt % (data_url, data_dir))                    
            fname = data_dir + "/" + data_file
            fn = download_file(os.path.join(data_url, data_file), fname)

            cmnd = "cd " + data_dir + "; " + "tar xf " + data_file
            os.system(cmnd)


        if not os.path.exists(owls_ion_path):
            raise RuntimeError, "Failed to download owls ion data."

        return owls_ion_path


class EagleNetworkFieldInfo(OWLSFieldInfo):

    _ions = \
        ('H1', 'H2', 'He1', 'He2','He3', 'C1',\
         'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'N1', 'N2', \
         'N3', 'N4', 'N5', 'N6', 'N7', 'N8', 'O1', 'O2', 'O3', \
         'O4', 'O5', 'O6', 'O7', 'O8', 'O9', 'Ne1', 'Ne2',\
         'Ne3', 'Ne4', 'Ne5', 'Ne6', 'Ne7', 'Ne8', 'Ne9', 'Ne10',\
         'Ne11', 'Mg1', 'Mg2', 'Mg3', 'Mg4', 'Mg5', 'Mg6', 'Mg7',\
         'Mg8', 'Mg9', 'Mg10', 'Mg11', 'Mg12', 'Mg13', 'Si1', 'Si2',\
         'Si3', 'Si4', 'Si5', 'Si6', 'Si7', 'Si8', 'Si9', 'Si10',\
         'Si11', 'Si12', 'Si13', 'Si14', 'Si15', 'Si16', 'Si17',\
         'Ca1', 'Ca2', 'Ca3', 'Ca4', 'Ca5', 'Ca6', 'Ca7', 'Ca8',\
         'Ca9', 'Ca10', 'Ca11', 'Ca12', 'Ca13', 'Ca14', 'Ca15',\
         'Ca16', 'Ca17', 'Ca18', 'Ca19', 'Ca20', 'Ca21', 'Fe1',\
         'Fe2', 'Fe3', 'Fe4', 'Fe5', 'Fe6', 'Fe7', 'Fe8', 'Fe9',\
         'Fe10', 'Fe11', 'Fe12', 'Fe13', 'Fe14', 'Fe15', 'Fe16',\
         'Fe17', 'Fe18', 'Fe19', 'Fe20', 'Fe21', 'Fe22', 'Fe23',\
         'Fe24', 'Fe25', 'Fe25', 'Fe27',)

    def __init__(self, *args, **kwargs):
        
        super(EagleNetworkFieldInfo,self).__init__( *args, **kwargs )
        
    def _create_ion_density_func( self, ftype, ion ):
        """ returns a function that calculates the ion density of a particle. 
        """ 

        def _ion_density(field, data):

            # Lookup the index of the ion 
            index = eaglenetwork_ion_lookup[ion] 

            # Ion to hydrogen number density ratio
            ion_chem = data[ftype, "Chemistry_%03i"%index]

            # Mass of a single ion
            if ion[0:2].isalpha():
                symbol = ion[0:2].capitalize()
            else:
                symbol = ion[0:1].capitalize()
            m_ion = YTQuantity(periodic_table.elements_by_symbol[symbol].weight, 'amu')

            # hydrogen number density 
            n_H = data["PartType0", "H_number_density"] 

            return m_ion*ion_chem*n_H 
        
        return _ion_density
