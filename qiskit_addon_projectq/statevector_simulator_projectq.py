# -*- coding: utf-8 -*-

# Copyright 2018, IBM.
#
# This source code is licensed under the Apache License, Version 2.0 found in
# the LICENSE.txt file in the root directory of this source tree.

"""
Interface to ProjectQ C++ quantum circuit simulator.
"""

import logging

from qiskit.backends.local._simulatorerror import SimulatorError
from qiskit.backends.local.localjob import LocalJob
from qiskit_addon_projectq import QasmSimulatorProjectQ

logger = logging.getLogger(__name__)


class StatevectorSimulatorProjectQ(QasmSimulatorProjectQ):
    """ProjectQ C++ statevector simulator"""

    DEFAULT_CONFIGURATION = {
        'name': 'projectq_statevector_simulator',
        'url': 'https://github.com/QISKit/qiskit-addon-projectq',
        'simulator': True,
        'local': True,
        'description': 'A ProjectQ C++ statevector simulator for qobj files',
        'coupling_map': 'all-to-all',
        'basis_gates': 'u1,u2,u3,cx,id,h,s,t'
    }

    def __init__(self, configuration=None):
        super().__init__(configuration or self.DEFAULT_CONFIGURATION.copy())

    def run(self, qobj):
        """Run qobj asynchronously.

        Args:
            qobj (dict): job description

        Returns:
            LocalJob: derived from BaseJob
        """
        return LocalJob(self._run_job, qobj)

    def _run_job(self, qobj):
        """Run circuits in qobj and return the result

            Args:
                qobj (dict): all the information necessary
                    (e.g., circuit, backend and resources) for running a circuit

            Returns:
                Result: Result is a class including the information to be returned to users.
                    Specifically, result_list in the return contains the essential information,
                    which looks like this::

                        [{'data':
                        {
                          'statevector': array([sqrt(2)/2, 0, 0, sqrt(2)/2], dtype=object),
                        },
                        'status': 'DONE'
                        }]
        """

        self._validate(qobj)
        final_state_key = 32767  # Internal key for final state snapshot
        # Add final snapshots to circuits
        for circuit in qobj['circuits']:
            circuit['compiled_circuit']['operations'].append(
                {'name': 'snapshot', 'params': [final_state_key]})
        result = super()._run_job(qobj)
        # Extract final state snapshot and move to 'statevector' data field
        for res in result._result['result']:
            snapshots = res['data']['snapshots']
            if str(final_state_key) in snapshots:
                final_state_key = str(final_state_key)
            # Pop off final snapshot added above
            final_state = snapshots.pop(final_state_key, None)
            final_state = final_state['statevector'][0]
            # Add final state to results data
            res['data']['statevector'] = final_state
            # Remove snapshot dict if empty
            if snapshots == {}:
                res['data'].pop('snapshots', None)

        return result

    # TODO: Remove duplication between files in statevector_simulator_*.py:
    #       methods _validate and _set_shots_to_1
    def _validate(self, qobj):
        """Semantic validations of the qobj which cannot be done via schemas.
        Some of these may later move to backend schemas.

        1. No shots
        2. No measurements in the middle
        """
        self._set_shots_to_1(qobj, False)
        for circuit in qobj['circuits']:
            self._set_shots_to_1(circuit, True)
            for operator in circuit['compiled_circuit']['operations']:
                if operator['name'] in ['measure', 'reset']:
                    raise SimulatorError("In circuit {}: statevector simulator does "
                                         "not support measure or reset.".format(circuit['name']))

    def _set_shots_to_1(self, dictionary, include_name):
        if 'config' not in dictionary:
            dictionary['config'] = {}
        if 'shots' in dictionary['config'] and dictionary['config']['shots'] != 1:
            warn = 'statevector simulator only supports 1 shot. Setting shots=1'
            if include_name:
                warn += 'Setting shots=1 for circuit' + dictionary['name']
            warn += '.'
            logger.info(warn)
        dictionary['config']['shots'] = 1
