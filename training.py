#!/usr/bin/env python2
# encoding: utf-8

# Special training methods
# Make use of some wrappers from SEMf

import numpy as np
import time
from pprint import pformat as pf

# from SEMf import misc as m

from . import utils
from .logcfg import log
from .network import RapidRBMCurrentImprint

# RapidRBMCurrentImprint = m.ClassInSubprocess(RapidRBMCurrentImprint)

NEST_MAX_TIME = 26843545.5


def train_rbm_pcd(
        training_data=None, # binary nd.array
                            # shape (n_labels, n_samples, n_visible)
        num_steps=15000,
        num_hidden=None,
        eta=1e-4,
        bm_init_kwargs=None, # dict
        bm_settings=None,    # dict
        sim_setup_kwargs={"spike_precision" : "on_grid", "time_step": 0.1},
        seed=42,
        bm_type=RapidRBMCurrentImprint
    ):
    assert len(training_data.shape) == 3

    np.random.seed(seed)

    num_labels, num_samples, num_visible = training_data.shape

    final_bm_settings = {
            "current_wipe" : 10.,
            "current_imprint" : 10.,
            "current_force_spike" : 10.,

            "time_wipe" : 20.,
            "time_imprint" : 10.,
            "time_force_spike" : 10.,
            "time_sim_step" : 10.,
            "time_recon_step" : 10.,
        }

    bm_init_kwargs["num_units_per_layer"] = [num_visible, num_hidden]

    final_bm_settings.update(bm_settings)

    recon_step = final_bm_settings["time_recon_step"]

    def init_net():
        bm = bm_type(**bm_init_kwargs)
        bm.create_no_return(sim_setup_kwargs=sim_setup_kwargs)

        bm.update_factors[:, 0] = np.sqrt(eta)

        for s in bm.samplers:
            s.silent = True

        bm.auto_sync_biases = False

        for k,v in final_bm_settings.iteritems():
            setattr(bm, k, v)

        # bm.update_weights()

        return bm

    bm = init_net()

    sample_ids = np.random.randint(num_samples, size=num_steps)

    t_start = time.time()

    # set a random binary state in the beginning
    binary_state = np.ones(bm.num_samplers) + 1 # per default set nothing
    visible_state_model = np.random.randint(2, size=num_visible)

    i_l = 0 # which label
    for i_step, i_samples in enumerate(sample_ids):

        try:
            if i_step % int(num_steps / 20) == 0:
                log.info("Run #{}. [SimTime: {}ms] ETA: {}".format(i_step,
                    bm.time_current,
                    utils.get_eta_str(t_start, i_step, num_steps)))
        except ZeroDivisionError:
            pass


        visible_state_data = training_data[i_l, i_samples]
        binary_state = np.ones(bm.num_samplers) + 1 # per default set nothing
        binary_state[:num_visible] = visible_state_model
        bm.binary_state = binary_state

        bm.run()
        hidden_state_1 = bm.binary_state[num_visible:].copy()
        # log.info("Hidden state: " + pf(hidden_state))
        # log.info("Last spiketimes: " + pf(bm.last_spiketimes))

        bm.continue_run(recon_step)
        visible_state_model = bm.binary_state[:num_visible].copy()
        bm.continue_run(recon_step)
        hidden_state_2 = bm.binary_state[num_visible:].copy()
        # log.info("Visible state: " + pf(visible_state))
        # log.info("Last spiketimes: " + pf(bm.last_spiketimes))

        if bm.time_current > 0.95 * NEST_MAX_TIME:
            weights_theo = bm.weights_theo
            bm.kill()
            bm = init_net()
            bm.weights_theo = weights_theo
            # bm.update_weights()

        update_factors = bm.update_factors

        update_factors[:num_visible, 1] = visible_state_data
        update_factors[:num_visible, 2] = visible_state_model

        update_factors[num_visible:, 1] = hidden_state_1
        update_factors[num_visible:, 2] = hidden_state_2

        bias_update = eta * np.r_[visible_state_data - visible_state_model,
                hidden_state_1 - hidden_state_2]

        bm.biases_theo = bm.biases_theo + bias_update

        bm.update_factors = update_factors

        bm.queue_update()

        i_l = (i_l+1) % num_labels

    log.info(pf(bm.weights_theo))

    return bm.weights_theo

