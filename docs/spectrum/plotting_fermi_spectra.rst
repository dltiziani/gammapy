.. _plotting_fermi_spectra:

************************************
Plotting Fermi 2FHL and 3FGL spectra
************************************

.. currentmodule:: gammapy.spectrum

In the following we will show how to plot spectra for Fermi 2FHL and 3FGL
sources, by using the `~gammapy.spectrum.models.SpectralModel`, `~gammapy.spectrum.SpectrumButterfly`
and `~gammapy.spectrum.DifferentialFluxPoints` classes.


As a first example we plot the spectral energy distribution for the Crab,
namely ``'3FGL J0534.5+2201'`` and ``'2FHL J0534.5+2201'``, including best fit
model, butterfly and flux points. First we load the corresponding catalog from
`~gammapy.catalog` and access the data for the crab:

.. code-block:: python

    import matplotlib.pyplot as plt
    from gammapy.catalog import SourceCatalog3FGL, SourceCatalog2FHL

    plt.style.use('ggplot')

    # load catalogs
    fermi_3fgl = SourceCatalog3FGL()
    fermi_2fhl = SourceCatalog2FHL()

    # access crab data by corresponding identifier
    crab_3fgl = fermi_3fgl['3FGL J0534.5+2201']
    crab_2fhl = fermi_2fhl['2FHL J0534.5+2201']

First we plot the best fit model for the 3FGL model:

.. code-block:: python

    ax = crab_3fgl.spectral_model.plot(crab_3fgl.energy_range, energy_power=2,
                                       label='Fermi 3FGL', color='r',
                                       flux_unit='erg-1 cm-2 s-1')
    ax.set_ylim(1e-12, 1E-9)

The ``crab_3fgl.energy_range`` attribute specifies the energy range of the 3FGL
model. By setting the argument ``energy_power=2`` we can plot the actual energy
distribution instead of the differential flux density. The `~gammapy.spectrum.models.SpectralModel.plot`
method returns an `~matplotlib.axes.Axes` object that can be reused later to plot
additional information on it. Here we just modify the y-limits of the plot.

As the next step we compute the butterfly for the best fit model and add it to
the plot:

.. code-block:: python

    from gammapy.utils.energy import EnergyBounds

    # set up an energy array to evaluate the butterfly
    emin, emax = crab_3fgl.energy_range
    energy = EnergyBounds.equal_log_spacing(emin, emax, 100)
    butterfly_3fg = crab_3fgl.spectrum.butterfly(energy)

    butterfly_3fg.plot(crab_3fgl.energy_range, ax=ax, energy_power=2, color='r',
                       flux_unit='erg-1 cm-2 s-1')

Finally we add the flux points by calling:

.. code-block:: python

    crab_3fgl.flux_points.plot(ax=ax, energy_power=2, color='r',
                               flux_unit='erg-1 cm-2 s-1')


The same can be done with the 2FHL best fit model:

.. code-block:: python

    crab_2fhl.spectral_model.plot(crab_2fhl.energy_range, ax=ax, energy_power=2,
                                  c='g', label='Fermi 2FHL', flux_unit='erg-1 cm-2 s-1')

    # set up an energy array to evaluate the butterfly using the 2FHL energy range
    emin, emax = crab_2fhl.energy_range
    energy = EnergyBounds.equal_log_spacing(emin, emax, 100)
    butterfly_2fhl = crab_2fhl.spectrum.butterfly(energy)

    # plot butterfly and flux points
    butterfly_2fhl.plot(crab_2fhl.energy_range, ax=ax, energy_power=2, color='g',
                        flux_unit='erg-1 cm-2 s-1')
    crab_2fhl.flux_points.plot(ax=ax, energy_power=2, color='g',
                               flux_unit='erg-1 cm-2 s-1')


The final plot looks as following:

.. plot:: spectrum/plot_fermi_spectra.py
   :include-source:
