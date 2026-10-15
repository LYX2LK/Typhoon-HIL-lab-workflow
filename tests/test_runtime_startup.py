"""Startup checks must not query run state before loading a model."""
import unittest
from unittest.mock import Mock
from typhoon_lab.runtime import no_active_simulation


class StartupGuardTests(unittest.TestCase):
    def test_unloaded_session_does_not_query_running_state(self):
        hil = Mock()
        hil.get_model_file_path.return_value = None
        hil.is_simulation_running.side_effect = AssertionError(
            "running-state query would emit Model was not loaded"
        )
        no_active_simulation(hil)
        hil.is_simulation_running.assert_not_called()

    def test_loaded_running_session_is_preserved(self):
        hil = Mock()
        hil.get_model_file_path.return_value = "existing.cpd"
        hil.is_simulation_running.return_value = True
        with self.assertRaisesRegex(RuntimeError, "already has a running simulation"):
            no_active_simulation(hil)
        hil.stop_simulation.assert_not_called()
        hil.load_model.assert_not_called()

    def test_loaded_stopped_session_can_proceed(self):
        hil = Mock()
        hil.get_model_file_path.return_value = "existing.cpd"
        hil.is_simulation_running.return_value = False
        no_active_simulation(hil)
        hil.is_simulation_running.assert_called_once_with()

    def test_failed_path_query_is_not_treated_as_unloaded(self):
        for value in (False, ""):
            with self.subTest(value=value):
                hil = Mock()
                hil.get_model_file_path.return_value = value
                with self.assertRaisesRegex(RuntimeError, "loaded model"):
                    no_active_simulation(hil)
                hil.is_simulation_running.assert_not_called()

    def test_path_query_exception_is_not_suppressed(self):
        hil = Mock()
        hil.get_model_file_path.side_effect = OSError("API unavailable")
        with self.assertRaisesRegex(OSError, "API unavailable"):
            no_active_simulation(hil)
        hil.is_simulation_running.assert_not_called()


if __name__ == "__main__":
    unittest.main()
