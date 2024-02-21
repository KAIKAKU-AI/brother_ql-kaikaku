#!/usr/bin/env python

"""
Helpers for the subpackage brother_ql.backends

* device discovery
* printing
"""

import logging
import time

from brother_ql.backends import backend_factory, guess_backend
from brother_ql.reader import interpret_response

logger = logging.getLogger(__name__)


def discover(backend_identifier="linux_kernel"):

    be = backend_factory(backend_identifier)
    list_available_devices = be["list_available_devices"]
    # BrotherQLBackend = be["backend_class"]

    available_devices = list_available_devices()
    return available_devices


def send(
    instructions,
    printer_identifier=None,
    backend_identifier=None,
    blocking=True,
    timeout=5,
):
    """
    Send instruction bytes to a printer.

    :param bytes instructions: The instructions to be sent to the printer.
    :param str printer_identifier: Identifier for the printer.
    :param str backend_identifier: Can enforce the use of a specific backend.
    :param bool blocking: Indicates whether the function call should block while
    waiting for the completion of the printing.
    """

    status = {
        "instructions_sent": True,  # The instructions were sent to the printer.
        "outcome": "unknown",  # Description of the sending operation outcome: 'unknown', 'sent', 'printed', 'error'
        "printer_state": None,  # Contains printer state if backend supports reading back.
        "did_print": False,  # True if a print was produced. Defaults to False if outcome is uncertain.
        "ready_for_next_job": False,  # True if printer is ready for next instructions.
        # Defaults to False if state is unknown.
    }

    selected_backend = None
    if backend_identifier:
        selected_backend = backend_identifier
    else:
        try:
            selected_backend = guess_backend(printer_identifier)
        except Exception:
            logger.info(
                "No backend stated. Selecting the default linux_kernel backend."
            )
            selected_backend = "linux_kernel"

    be = backend_factory(selected_backend)
    # list_available_devices = be["list_available_devices"]
    BrotherQLBackend = be["backend_class"]

    printer = BrotherQLBackend(printer_identifier)

    start = time.time()
    logger.info(
        "Sending instructions to the printer. Total: %d bytes.", len(instructions)
    )
    printer.write(instructions)
    status["outcome"] = "sent"

    if not blocking:
        return status
    if selected_backend == "network":
        """No need to wait for completion. The network backend doesn't support readback."""
        return status

    while time.time() - start < timeout:
        data = printer.read()
        if not data:
            time.sleep(0.005)
            continue
        try:
            result = interpret_response(data)
        except ValueError:
            logger.error(
                "TIME %.3f - Couln't understand response: %s", time.time() - start, data
            )
            continue
        status["printer_state"] = result
        logger.debug("TIME %.3f - result: %s", time.time() - start, result)
        if result["errors"]:
            logger.error("Errors occured: %s", result["errors"])
            status["outcome"] = "error"
            break
        if result["status_type"] == "Printing completed":
            status["did_print"] = True
            status["outcome"] = "printed"
        if (
            result["status_type"] == "Phase change"
            and result["phase_type"] == "Waiting to receive"
        ):
            status["ready_for_next_job"] = True
        if status["did_print"] and status["ready_for_next_job"]:
            break

    if not status["did_print"]:
        logger.warning("'printing completed' status not received.")
    if not status["ready_for_next_job"]:
        logger.warning("'waiting to receive' status not received.")
    if (not status["did_print"]) or (not status["ready_for_next_job"]):
        logger.warning("Printing potentially not successful?")
    if status["did_print"] and status["ready_for_next_job"]:
        logger.info("Printing was successful. Waiting for the next job.")

    return status
