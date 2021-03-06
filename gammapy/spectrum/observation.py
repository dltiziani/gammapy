# Licensed under a 3-clause BSD style license - see LICENSE.rst
from __future__ import absolute_import, division, print_function, unicode_literals
import numpy as np
from copy import deepcopy
from astropy.extern.six.moves import UserList
from astropy.units import Quantity
from ..extern.pathlib import Path
from ..utils.scripts import make_path
from ..utils.energy import EnergyBounds
from ..utils.fits import table_from_row_data
from ..data import ObservationStats
from ..irf import EffectiveAreaTable, EnergyDispersion
from .core import CountsSpectrum, PHACountsSpectrum
from .utils import calculate_predicted_counts

__all__ = [
    'SpectrumStats',
    'SpectrumObservation',
    'SpectrumObservationList',
    'SpectrumObservationStacker',
]


class SpectrumStats(ObservationStats):
    """Spectrum stats.

    Extends `~gammapy.data.ObservationStats` with spectrum
    specific information (energy bin info at the moment).
    """

    def __init__(self, **kwargs):
        self.energy_min = kwargs.pop('energy_min', None)
        self.energy_max = kwargs.pop('energy_max', None)
        super(SpectrumStats, self).__init__(**kwargs)

    def __str__(self):
        ss = super(SpectrumStats, self).__str__()
        ss += 'energy range: {:.2f} - {:.2f}'.format(self.energy_min, self.energy_max)
        return ss

    def to_dict(self):
        """TODO: document"""
        data = super(SpectrumStats, self).to_dict()
        data['energy_min'] = self.energy_min
        data['energy_max'] = self.energy_max
        return data


class SpectrumObservation(object):
    """1D spectral analysis storage class

    This container holds the ingredients for 1D region based spectral analysis
    TODO: describe PHA, ARF, etc.

    Meta data is stored in the ``on_vector`` attribute. This reflects the OGIP
    convention.

    Parameters
    ----------
    on_vector : `~gammapy.spectrum.PHACountsSpectrum`
        On vector
    aeff : `~gammapy.irf.EffectiveAreaTable`
        Effective Area
    off_vector : `~gammapy.spectrum.PHACountsSpectrum`, optional
        Off vector
    edisp : `~gammapy.irf.EnergyDispersion`, optional
        Energy dispersion matrix

    Examples
    --------

    ::
        from gammapy.spectrum import SpectrumObservation
        filename = '$GAMMAPY_EXTRA/datasets/hess-crab4_pha/pha_obs23523.fits'
        obs = SpectrumObservation.read(filename)
        print(obs)
    """

    def __init__(self, on_vector, aeff, off_vector=None, edisp=None):
        self.on_vector = on_vector
        self.aeff = aeff
        self.off_vector = off_vector
        self.edisp = edisp

    @property
    def obs_id(self):
        """Unique identifier"""
        return self.on_vector.obs_id

    @obs_id.setter
    def obs_id(self, obs_id):
        self.on_vector.obs_id = obs_id
        if self.off_vector is not None:
            self.off_vector.obs_id = obs_id

    @property
    def livetime(self):
        """Dead-time corrected observation time"""
        return self.on_vector.livetime

    @property
    def alpha(self):
        """Exposure ratio between signal and background regions"""
        return self.on_vector.backscal / self.off_vector.backscal

    @property
    def e_reco(self):
        """Reconstruced energy bounds array."""
        return EnergyBounds(self.on_vector.energy.data)

    @property
    def e_true(self):
        """True energy bounds array."""
        return EnergyBounds(self.aeff.energy.data)

    @property
    def nbins(self):
        """Number of reconstruced energy bins"""
        return self.on_vector.energy.nbins

    @property
    def lo_threshold(self):
        """Low energy threshold"""
        return self.on_vector.lo_threshold

    @lo_threshold.setter
    def lo_threshold(self, threshold):
        self.on_vector.lo_threshold = threshold
        if self.off_vector is not None:
            self.off_vector.lo_threshold = threshold

    @property
    def hi_threshold(self):
        """High energy threshold"""
        return self.on_vector.hi_threshold

    @hi_threshold.setter
    def hi_threshold(self, threshold):
        self.on_vector.hi_threshold = threshold
        if self.off_vector is not None:
            self.off_vector.hi_threshold = threshold

    @property
    def background_vector(self):
        """Background `~gammapy.spectrum.CountsSpectrum`

        bkg = alpha * n_off

        If alpha is a function of energy this will differ from
        self.on_vector * self.total_stats.alpha because the latter returns an
        average value for alpha.
        """
        energy = self.off_vector.energy
        data = self.off_vector.data * self.alpha
        return CountsSpectrum(data=data, energy=energy)

    @property
    def total_stats(self):
        """Return total `~gammapy.spectrum.SpectrumStats`
        """
        return self.stats_in_range(0, self.nbins-1)

    @property
    def total_stats_safe_range(self):
        """Return total `~gammapy.spectrum.SpectrumStats` within the tresholds
        """
        safe_bins = self.on_vector.bins_in_safe_range
        return self.stats_in_range(safe_bins[0], safe_bins[-1])

    def stats_in_range(self, bin_min, bin_max):
        """Compute stats for a range of energy bins
        
        Parameters
        ----------
        bin_min, bin_max: int
            Bins to include

        Returns
        -------
        stats : `~gammapy.spectrum.SpectrumStats`
            Stacked stats
        """
        idx = np.arange(bin_min, bin_max)
        stats_list = [self.stats(ii) for ii in idx] 
        stacked_stats = SpectrumStats.stack(stats_list)
        stacked_stats.livetime = self.livetime
        stacked_stats.obs_id = self.obs_id
        stacked_stats.energy_min = self.e_reco[bin_min]
        stacked_stats.energy_max = self.e_reco[bin_max + 1]
        return stacked_stats

    def stats(self, idx):
        """Compute stats for one energy bin.

        Parameters
        ----------
        idx : int
            Energy bin index

        Returns
        -------
        stats : `~gammapy.spectrum.SpectrumStats`
            Stats
        """
        return SpectrumStats(
            energy_min=self.e_reco[idx],
            energy_max=self.e_reco[idx + 1],
            n_on=int(self.on_vector.data.value[idx]),
            n_off=int(self.off_vector.data.value[idx]),
            a_on=self.on_vector._backscal_array[idx],
            a_off=self.off_vector._backscal_array[idx],
            obs_id=self.obs_id,
            livetime=self.livetime,
        )

    def stats_table(self):
        """Per-bin stats as a table.

        Returns
        -------
        table : `~astropy.table.Table`
            Table with stats for one energy bin in one row.
        """
        rows = [self.stats(idx).to_dict() for idx in range(len(self.e_reco) - 1)]
        return table_from_row_data(rows=rows)

    def predicted_counts(self, model):
        """Calculated npred given a model

        Parameters
        ----------
        model : `~gammapy.spectrum.models.SpectralModel`
            Spectral model

        Returns
        -------
        npred : `~gammapy.spectrum.CountsSpectrum`
            Predicted counts
        """
        return calculate_predicted_counts(model=model,
                                          edisp=self.edisp,
                                          aeff=self.aeff,
                                          livetime=self.livetime)

    @classmethod
    def read(cls, filename):
        """Read `~gammapy.spectrum.SpectrumObservation` from OGIP files.

        BKG file, ARF, and RMF must be set in the PHA header and be present in
        the same folder.

        Parameters
        ----------
        filename : str
            OGIP PHA file to read
        """
        filename = make_path(filename)
        dirname = filename.parent
        on_vector = PHACountsSpectrum.read(filename)
        rmf, arf, bkg = on_vector.rmffile, on_vector.arffile, on_vector.bkgfile
        try:
            energy_dispersion = EnergyDispersion.read(str(dirname / rmf))
        except IOError:
            # TODO : Add logger and echo warning
            energy_dispersion = None
        try:
            off_vector = PHACountsSpectrum.read(str(dirname / bkg))
        except IOError:
            # TODO : Add logger and echo warning
            off_vector = None

        effective_area = EffectiveAreaTable.read(str(dirname / arf))
        return cls(on_vector=on_vector,
                   aeff=effective_area,
                   off_vector=off_vector,
                   edisp=energy_dispersion)

    def write(self, outdir=None, use_sherpa=False, overwrite=True):
        """Write OGIP files

        If you want to use the written files with Sherpa you have to set the
        ``use_sherpa`` flag. Then all files will be written in units 'keV' and
        'cm2'.

        Parameters
        ----------
        outdir : `~gammapy.extern.pathlib.Path`
            output directory, default: pwd
        use_sherpa : bool, optional
            Write Sherpa compliant files, default: False
        overwrite : bool, optional
            Overwrite, default: True
        """

        outdir = Path.cwd() if outdir is None else Path(outdir)
        outdir.mkdir(exist_ok=True, parents=True)

        phafile = self.on_vector.phafile
        bkgfile = self.on_vector.bkgfile
        arffile = self.on_vector.arffile
        rmffile = self.on_vector.rmffile

        # Write in keV and cm2 for sherpa
        if use_sherpa:
            self.on_vector.energy.data = self.on_vector.energy.data.to('keV')
            self.aeff.energy.data = self.aeff.energy.data.to('keV')
            self.aeff.data = self.aeff.data.to('cm2')
            if self.off_vector is not None:
                self.off_vector.energy.data = self.off_vector.energy.data.to('keV')
            if self.edisp is not None:
                self.edisp.e_reco.data = self.edisp.e_reco.data.to('keV')
                self.edisp.e_true.data = self.edisp.e_true.data.to('keV')
                # Set data to itself to trigger reset of the interpolator
                # TODO: Make NDData notice change of axis
                self.edisp.data = self.edisp.data

        self.on_vector.write(outdir / phafile, clobber=overwrite)
        self.aeff.write(outdir / arffile, clobber=overwrite)
        if self.off_vector is not None:
            self.off_vector.write(outdir / bkgfile, clobber=overwrite)
        if self.edisp is not None:
            self.edisp.write(str(outdir / rmffile), clobber=overwrite)

    def peek(self, figsize=(15, 15)):
        """Quick-look summary plots."""
        import matplotlib.pyplot as plt

        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(nrows=2, ncols=2, figsize=figsize)

        ax1.set_title('Counts')
        energy_unit = 'TeV'
        if self.off_vector is not None:
            self.background_vector.plot_hist(ax=ax1,
                                             label='alpha * n_off',
                                             color='darkblue',
                                             energy_unit=energy_unit)
        self.on_vector.plot_hist(ax=ax1,
                                 label='n_on',
                                 color='darkred',
                                 energy_unit=energy_unit,
                                 show_energy=(self.hi_threshold, self.lo_threshold))
        ax1.set_xlim(0.7 * self.lo_threshold.to(energy_unit).value,
                     1.3 * self.hi_threshold.to(energy_unit).value)
        ax1.legend(numpoints=1)

        ax2.set_title('Effective Area')
        e_unit = self.aeff.energy.unit
        self.aeff.plot(ax=ax2,
                       show_energy=(self.hi_threshold, self.lo_threshold))
        ax2.set_xlim(0.7 * self.lo_threshold.to(e_unit).value,
                     1.3 * self.hi_threshold.to(e_unit).value)

        ax3.axis('off')
        if self.off_vector is not None:
            ax3.text(0, 0.3, '{}'.format(self.total_stats_safe_range), fontsize=18)

        ax4.set_title('Energy Dispersion')
        if self.edisp is not None:
            self.edisp.plot_matrix(ax=ax4)

        # TODO: optimize layout
        # plt.subplots_adjust(hspace = .2, left=.1)
        return fig

    def to_sherpa(self):
        """Create a `~sherpa.astro.data.DataPHA`

        associated background vectors and IRFs are also translated to sherpa
        objects and appended to the PHA instance
        """
        pha = self.on_vector.to_sherpa(name='pha_obs{}'.format(self.obs_id))
        arf = self.aeff.to_sherpa(name='arf_obs{}'.format(self.obs_id))
        if self.edisp is not None:
            rmf = self.edisp.to_sherpa(name='rmf_obs{}'.format(self.obs_id))
        else:
            rmf = None

        pha.set_response(arf, rmf)

        if self.off_vector is not None:
            bkg = self.off_vector.to_sherpa(name='bkg_obs{}'.format(self.obs_id))
            bkg.set_response(arf, rmf)
            pha.set_background(bkg, 1)

        # see https://github.com/sherpa/sherpa/blob/36c1f9dabb3350b64d6f54ab627f15c862ee4280/sherpa/astro/data.py#L1400
        pha._set_initial_quantity()
        return pha

    def __str__(self):
        """String representation"""
        ss = self.total_stats_safe_range.__str__()
        return ss

    def _check_binning(self, **kwargs):
        """Check that ARF and RMF binnings are compatible
        """
        raise NotImplementedError

    def copy(self):
        """A deep copy of self.
        """
        return deepcopy(self)


class SpectrumObservationList(UserList):
    """
    List of `~gammapy.spectrum.SpectrumObservation`.
    """

    def obs(self, obs_id):
        """Return one observation

        Parameters
        ----------
        obs_id : int
            Identifier
        """
        obs_id_list = [o.obs_id for o in self]
        idx = obs_id_list.index(obs_id)
        return self[idx]

    def __str__(self):
        ss = self.__class__.__name__
        ss += '\n{}'.format(self.obs_id)
        return ss

    @property
    def obs_id(self):
        return [o.obs_id for o in self]

    @property
    def total_livetime(self):
        livetimes = [o.livetime.to('s').value for o in self]
        return Quantity(np.sum(livetimes), 's')

    def stack(self):
        """Return stacked `~gammapy.spectrum.SpectrumObservation`"""
        stacker = SpectrumObservationStacker(obs_list=self)
        stacker.run()
        return stacker.stacked_obs

    def write(self, outdir=None, **kwargs):
        """Create OGIP files

        Parameters
        ----------
        outdir : str, `~gammapy.extern.pathlib.Path`, optional
            Output directory, default: pwd
        """
        for obs in self:
            obs.write(outdir=outdir, **kwargs)

    @classmethod
    def read(cls, directory):
        """Read multiple observations
        
        This methods reads all PHA files contained in a given directory

        Parameters
        ----------
        directory : `~gammapy.extern.pathlib.Path`
            Directory holding the observations
        """
        obs_list = cls()
        directory = make_path(directory)
        filelist = directory.glob('pha*.fits')
        for phafile in filelist:
            obs = SpectrumObservation.read(phafile)
            obs_list.append(obs)
        return obs_list
    

class SpectrumObservationStacker(object):
    r"""Stack `~gammapy.spectrum.SpectrumObervationList`

    The stacking of :math:`j` observations is implemented as follows.
    :math:`k` and :math:`l` denote a bin in reconstructed and true energy,
    respectively. 

    .. math:: 

        \epsilon_{jk} =\left\{\begin{array}{cl} 1, & \mbox{if
            bin k is inside the energy thresholds}\\ 0, & \mbox{otherwise} \end{array}\right.

        \overline{\mathrm{n_{on}}}_k = \sum_{j} \mathrm{n_{on}}_{jk} \cdot
            \epsilon_{jk} 

        \overline{\mathrm{n_{off}}}_k = \sum_{j} \mathrm{n_{off}}_{jk} \cdot
            \epsilon_{jk} 

        \overline{\alpha}_k = \frac{\sum_{j}\alpha_{jk} \cdot
            \mathrm{n_{off}}_{jk} \cdot \epsilon_{jk}}{\overline{\mathrm {n_{off}}}}

        \overline{t} = \sum_{j} t_i

        \overline{\mathrm{aeff}}_l = \frac{\sum_{j}\mathrm{aeff}_{jl} 
            \cdot t_j}{\overline{t}}

        \overline{\mathrm{edisp}}_{kl} = \frac{\sum_{j} \mathrm{edisp}_{jkl} 
            \cdot \mathrm{aeff}_{jl} \cdot t_j \cdot \epsilon_{jk}}{\sum_{j} \mathrm{aeff}_{jl}
            \cdot t_j}

    Parameters
    ----------
    obs_list : `~gammapy.spectrum.SpectrumObservationList`
        Observations to stack

    Examples
    --------
    >>> from gammapy.spectrum import SpectrumObservationList, SpectrumObservationStacker
    >>> obs_list = SpectrumObservationList.read('$GAMMAPY_EXTRA/datasets/hess-crab4_pha')
    >>> obs_stacker = SpectrumObservationStacker(obs_list)
    >>> obs_stacker.run()
    >>> print(obs_stacker.stacked_obs)
    *** Observation summary report ***
    Observation Id: [23523-23592]
    Livetime: 0.879 h
    On events: 279
    Off events: 108
    Alpha: 0.037
    Bkg events in On region: 3.96
    Excess: 275.04
    Excess / Background: 69.40
    Gamma rate: 0.14 1 / min
    Bkg rate: 0.00 1 / min
    Sigma: 37.60
    energy range: 681292069.06 keV - 87992254356.91 keV
    """

    def __init__(self, obs_list):
        self.obs_list = SpectrumObservationList(obs_list)
        self.stacked_on_vector = None
        self.stacked_off_vector = None
        self.stacked_aeff = None
        self.stacked_edisp = None
        self.stacked_bkscal_on = None
        self.stacked_bkscal_off = None
        self.stacked_obs = None

    def __str__(self):
        ss = self.__class__.__name__
        ss += '\n{}'.format(self.obs_list)
        return ss

    def run(self):
        """Run all steps in the correct order"""
        self.stack_counts_vectors()
        self.stack_aeff()
        self.stack_edisp()
        self.stack_obs()

    def stack_counts_vectors(self):
        """Stack on and off vector"""
        self.stack_on_vector()
        self.stack_off_vector()
        self.stack_backscal()
        self.setup_counts_vectors()

    def stack_on_vector(self):
        on_vector_list = [o.on_vector for o in self.obs_list]
        self.stacked_on_vector = self.stack_counts_spectrum(on_vector_list)

    def stack_off_vector(self):
        off_vector_list = [o.off_vector for o in self.obs_list]
        self.stacked_off_vector = self.stack_counts_spectrum(off_vector_list)

    @staticmethod
    def stack_counts_spectrum(counts_spectrum_list):
        """Stack `~gammapy.spectrum.PHACountsSpectrum`

        Bins outside the safe energy range are set to 0, attributes
        are set to None.
        """
        template = counts_spectrum_list[0].copy()
        energy = template.energy
        stacked_data = np.zeros(energy.nbins)
        stacked_quality = np.zeros(energy.nbins)
        for spec in counts_spectrum_list:
            stacked_data += spec.counts_in_safe_range
            stacked_quality = np.logical_or(stacked_quality,
                                            spec.quality)

        stacked_spectrum = PHACountsSpectrum(data=stacked_data,
                                             energy=energy,
                                             quality=stacked_quality)
        return stacked_spectrum

    def stack_backscal(self):
        """Stack backscal for on and off vector
        """
        nbins = self.obs_list[0].e_reco.nbins
        bkscal_on = np.zeros(nbins)
        bkscal_off = np.zeros(nbins)

        for o in self.obs_list:
            bkscal_on_data = o.on_vector._backscal_array.copy()
            bkscal_on += bkscal_on_data * o.off_vector.counts_in_safe_range

            bkscal_off_data = o.off_vector._backscal_array.copy()
            bkscal_off += bkscal_off_data * o.off_vector.counts_in_safe_range

        stacked_bkscal_on = bkscal_on / self.stacked_off_vector.data
        stacked_bkscal_off = bkscal_off / self.stacked_off_vector.data

        # there should be no nan values in backscal_on or backscal_off
        # this leads to problems when fitting the data
        alpha_correction = - 1
        idx = np.where(self.stacked_off_vector.data == 0)[0]
        stacked_bkscal_on[idx] = alpha_correction
        stacked_bkscal_off[idx] = alpha_correction

        self.stacked_bkscal_on = stacked_bkscal_on
        self.stacked_bkscal_off = stacked_bkscal_off

    def setup_counts_vectors(self):
        """Add correct attributes to stacked counts vectors"""
        total_livetime = self.obs_list.total_livetime
        self.stacked_on_vector.livetime = total_livetime
        self.stacked_off_vector.livetime = total_livetime
        self.stacked_on_vector.backscal = self.stacked_bkscal_on
        self.stacked_off_vector.backscal = self.stacked_bkscal_off
        self.stacked_on_vector.obs_id = self.obs_list.obs_id
        self.stacked_off_vector.obs_id = self.obs_list.obs_id

    def stack_aeff(self):
        """Stack effective areas (weighted by livetime)

        TODO: Refactor into staticmethod?
        """
        nbins = self.obs_list[0].e_true.nbins
        aefft = Quantity(np.zeros(nbins), 'cm2 s')
        for o in self.obs_list:
            aeff_data = o.aeff.evaluate(fill_nan=True)
            aefft_current = aeff_data * o.livetime
            aefft += aefft_current

        # TODO: Save aefft to reuse it in stack_edisp?
        stacked_data = aefft / self.obs_list.total_livetime
        self.stacked_aeff = EffectiveAreaTable(energy=self.obs_list[0].e_true,
                                               data=stacked_data.to('cm2'))

    def stack_edisp(self):
        """Stack energy dispersion (weighted by exposure)"""

        reco_bins = self.obs_list[0].e_reco.nbins
        true_bins = self.obs_list[0].e_true.nbins

        aefft = Quantity(np.zeros(true_bins), 'cm2 s')
        temp = np.zeros(shape=(reco_bins, true_bins))
        aefftedisp = Quantity(temp, 'cm2 s')

        for o in self.obs_list:
            aeff_data = o.aeff.evaluate(fill_nan=True)
            aefft_current = aeff_data * o.livetime
            aefft += aefft_current
            edisp_data = o.edisp.pdf_in_safe_range(o.lo_threshold, o.hi_threshold)
            aefftedisp += edisp_data.transpose() * aefft_current

        stacked_edisp = np.nan_to_num(aefftedisp / aefft)

        self.stacked_edisp = EnergyDispersion(e_true=self.obs_list[0].e_true,
                                              e_reco=self.obs_list[0].e_reco,
                                              data=stacked_edisp.transpose())

    def stack_obs(self):
        """Create stacked `~gammapy.spectrum.SpectrumObservation`"""
        obs = SpectrumObservation(on_vector=self.stacked_on_vector,
                                  off_vector=self.stacked_off_vector,
                                  aeff=self.stacked_aeff,
                                  edisp=self.stacked_edisp
                                  )
        self.stacked_obs = obs
