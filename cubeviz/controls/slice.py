import numpy as np

from glue.core import HubListener
from specviz.third_party.glue.data_viewer import dispatch as specviz_dispatch

from ..messages import SliceIndexUpdateMessage
from .units import REST_WAVELENGTH_TEXT, OBS_WAVELENGTH_TEXT

RED_BACKGROUND = "background-color: rgba(255, 0, 0, 128);"

import logging
logging.basicConfig(format='%(levelname)-6s: %(name)-10s %(asctime)-15s  %(message)s')
log = logging.getLogger("SliceController")
log.setLevel(logging.DEBUG)

class SliceController(HubListener):

    def __init__(self, cubeviz_layout):
        self._cv_layout = cubeviz_layout
        self._hub = cubeviz_layout.session.hub
        ui = cubeviz_layout.ui

        # These are the contents of the text boxes
        self._slice_textbox = ui.slice_textbox
        self._wavelength_textbox = ui.wavelength_textbox

        # This is the slider widget itself
        self._slice_slider = ui.slice_slider

        # This is the label for the wavelength units
        self._wavelength_textbox_label = ui.wavelength_textbox_label

        self._slice_slider.valueChanged.connect(self._on_slider_change)
        self._slice_slider.sliderPressed.connect(self._on_slider_pressed)
        self._slice_slider.sliderReleased.connect(self._on_slider_released)
        self._slider_flag = False

        self._slice_textbox.returnPressed.connect(self._on_text_slice_change)
        self._wavelength_textbox.returnPressed.connect(self._on_text_wavelength_change)

        self._slice_slider.setEnabled(False)
        self._slice_textbox.setEnabled(False)
        self._wavelength_textbox.setEnabled(False)
        self._wavelength_textbox_label.setWordWrap(True)

        # This should be used to distinguised between observed and rest wavelengths
        # We are not going to enforce what the name should be at this level.
        self._wavelength_label_text = OBS_WAVELENGTH_TEXT

        self._wavelength_format = '{}'
        self._wavelength_units = None
        self._wavelengths = None

        # Connect this class to specviz's event dispatch so methods can listen
        # to specviz events
        specviz_dispatch.setup(self)

    @property
    def wavelength_label(self):
        """
        Get the wavelength label, though this probably will not be used much.
        """
        return self._wavelength_label_text

    @wavelength_label.setter
    def wavelength_label(self, new_label):
        """
        Set the wavelength label. The new label should probably be "Obs Wavelength"
        or "Rest Wavelength" but maybe could be other things.

        :return: None
        """
        self._wavelength_label_text = new_label

        self._wavelength_textbox_label.setText('{} ({})'.format(
            self._wavelength_label_text, self._wavelength_units))

    def enable(self, wcs, wavelengths):
        """
        Setup the slice slider (min/max, units on description and initial position).

        :return:
        """
        self.set_enabled(True)

        self._hub.subscribe(self, SliceIndexUpdateMessage, handler=self.master_index_update)

        self._slice_slider.setMinimum(0)

        # Store the wavelength units and format
        self._wavelength_units = str(wcs.wcs.cunit[2])
        self._wavelength_format = '{:.3}'
        self._wavelength_textbox_label.setText('{} ({})'.format(
            self._wavelength_label_text, self._wavelength_units))

        # Grab the wavelengths so they can be displayed in the text box
        self._wavelengths = wavelengths
        self._slice_slider.setMaximum(len(self._wavelengths) - 1)

        # Set the default display to the middle of the cube
        middle_index = len(self._wavelengths) // 2
        self._slice_slider.setValue(middle_index)
        self._wavelength_textbox.setText(self._wavelength_format.format(self._wavelengths[middle_index]))

        self._cv_layout.synced_index = middle_index

    def set_enabled(self, value):
        self._slice_slider.setEnabled(value)
        self._slice_textbox.setEnabled(value)
        self._wavelength_textbox.setEnabled(value)

    def set_wavelengths(self, new_wavelengths, new_units):
        # Store the wavelength units and format
        new_units_name = new_units.short_names[0]
        self._wavelength_units = new_units_name
        self._wavelength_format = '{:.3}'
        self._wavelength_textbox_label.setText('{} ({})'.format(
            self._wavelength_label_text, self._wavelength_units))

        # Grab the wavelengths so they can be displayed in the text box
        self._wavelengths = new_wavelengths
        self._slice_slider.setMaximum(len(self._wavelengths) - 1)

        self._wavelength_textbox.setText(self._wavelength_format.format(self._wavelengths[self._cv_layout.synced_index]))

        specviz_dispatch.changed_units.emit(x=new_units)

    def get_index(self):
        return self._cv_layout.synced_index

    def update_index(self, index):
        self._slice_slider.setValue(index)

    def change_slider_value(self, amount):
        new_index = self._slice_slider.value() + amount
        self._slice_slider.setValue(new_index)

        specviz_dispatch.changed_dispersion_position.emit(pos=new_index)

    def master_index_update(self, message):
        index = message.index

        try:
            tb_index = int(self._slice_textbox.text())
        except ValueError:
            tb_index = -1

        if tb_index != index:
            self._slice_textbox.setText(str(index))

        try:
            wavelength = float(self._wavelength_textbox.text())
            wv_index = np.argsort(abs(self._wavelengths - wavelength))[0]
        except ValueError:
            wavelength = -1
            wv_index = -1

        if index != wv_index:
            self._wavelength_textbox.setText(str(self._wavelengths[index]))

        slider_index = self._slice_slider.value()
        if slider_index != index:
            self._slice_slider.setValue(index)

        self.apply_to_viewers(index)

    def _on_slider_change(self, event):
        """
        Callback for change in slider value.

        :param event:
        :return:
        """
        index = self._slice_slider.value()
        msg = SliceIndexUpdateMessage(self, index, self._cv_layout.session.data_collection[0])
        self._hub.broadcast(msg)

    def apply_to_viewers(self, index):
        cube_views = self._cv_layout.cube_views
        active_cube = self._cv_layout._active_cube
        active_widget = active_cube._widget

        # If the active widget is synced then we need to update the image
        # in all the other synced views.
        if active_widget.synced and not self._cv_layout._single_viewer_mode:
            for view in cube_views:
                if view._widget.synced:
                    if self._slider_flag:
                        view._widget.fast_draw_slice_at_index(index)
                    else:
                        view._widget.update_slice_index(index)
            self._cv_layout.synced_index = index
        else:
            # Update the image displayed in the slice in the active view
            if self._slider_flag:
                active_widget.fast_draw_slice_at_index(index)
            else:
                active_widget.update_slice_index(index)

        specviz_dispatch.changed_dispersion_position.emit(pos=index)

    def _on_slider_pressed(self):
        """
        Callback for slider pressed.
        activates fast_draw_slice_at_index flags
        """
        # This flag will activate fast_draw_slice_at_index
        # Which will redraw sliced images quickly
        self._slider_flag = True

    @specviz_dispatch.register_listener("finished_position_change")
    def _on_slider_released(self):
        """
        Callback for slider released (includes specviz slider).
        Dactivates fast_draw_slice_at_index flags
        Will do a full redraw of all synced viewers.
        This is considered the final redraw after fast_draw_slice_at_index
        blits images to the viewers. This function will redraw the axis,
        tites, labels etc...
        """
        # This flag will deactivate fast_draw_slice_at_index
        self._slider_flag = False

        index = self._slice_slider.value()
        cube_views = self._cv_layout.cube_views
        active_cube = self._cv_layout._active_cube
        active_widget = active_cube._widget

        # If the active widget is synced then we need to update the image
        # in all the other synced views.
        if active_widget.synced and not self._cv_layout._single_viewer_mode:
            for view in cube_views:
                if view._widget.synced:
                    view._widget.update_slice_index(index)
            self._cv_layout.synced_index = index
        else:
            # Update the image displayed in the slice in the active view
            active_widget.update_slice_index(index)

        specviz_dispatch.changed_dispersion_position.emit(pos=index)

    #@glue_subscribe(SliceIndexUpdateMessage)
    def _update_slice_textboxes(self, message):
        """
        Update the slice index number text box and the wavelength value displayed in the wavelengths text box.

        :param index: Slice index number displayed.
        :return:
        """
        index = message.index

        # Update the input text box for slice number
        self._slice_textbox.setText(str(index))

        # Update the wavelength for the corresponding slice number.
        self._wavelength_textbox.setText(self._wavelength_format.format(self._wavelengths[index]))

    def _on_text_slice_change(self, event=None):
        """
        Callback for a change in the slice index text box.  We will need to
        update the slider and the wavelength value when this changes.

        :param event:
        :return:
        """
        # Get the value they typed in, but if not a number, then let's just use
        # the first slice.
        try:
            index = int(self._slice_textbox.text())
            self._slice_textbox.setStyleSheet("")
        except ValueError:
            self._slice_textbox.setStyleSheet(RED_BACKGROUND)
            return

        if index == self._slice_textbox.text():
            return

        # If a number and out of range then set to the first or last slice
        # depending if they set the number too low or too high.
        if index < 0:
            index = 0
        if index > len(self._wavelengths) - 1:
            index = len(self._wavelengths) - 1

        # Update the slider.
        self._slice_slider.setValue(index)

    def _on_text_wavelength_change(self, event=None, pos=None):
        """
        Callback for a change in wavelength input box. We want to find the
        closest wavelength and use the index of it.  We will need to update the
        slice index box and slider as well as the image.

        :param event:
        :param pos: This is the argument used by the specviz event listener to
                    update the CubeViz slider and associated text based on the
                    movement of the SpecViz position bar. The name of this
                    argument cannot change since it is the one expected by the
                    SpecViz event system.
        :return:
        """
        try:
            # Find the closest real wavelength and use the index of it
            wavelength = pos if pos is not None else float(self._wavelength_textbox.text())
            index = np.argsort(abs(self._wavelengths - wavelength))[0]
            self._wavelength_textbox.setStyleSheet("")
        except ValueError:
            self._wavelength_textbox.setStyleSheet(RED_BACKGROUND)
            return

        # Update the slider.
        self._slice_slider.setValue(index)

    @specviz_dispatch.register_listener("change_dispersion_position")
    def specviz_wavelength_slider_change(self, event=None, pos=None):
        """
        SpecViz slider index changed callback
        """
        # if self._slider_flag is active then
        # something else is using it so don't
        # deactivate it when done (deactivate_flag)
        if self._slider_flag:
            deactivate_flag = False
        else:
            deactivate_flag = True
            self._slider_flag = True

        # The "pos" value coming from specviz appears to be related to the
        # index in the observed wavelength and so if there is a redshift
        # then we need to convert the pos to the rest wavelength position.
        if self._cv_layout._units_controller and not self._cv_layout._units_controller.redshift_z == 0.0:
            rest_wavelength = pos / (1 + self._cv_layout._units_controller.redshift_z)
            pos = np.argsort(abs(self._wavelengths - rest_wavelength))[0]

            # Pos is a wavelength and not an index for the call back for specviz
            pos = self._wavelengths[pos]

        self._on_text_wavelength_change(event, pos)

        if deactivate_flag:
            self._slider_flag = False
