import concurrent.futures
from typing import Any, cast, List, Optional, Tuple, TYPE_CHECKING
import weakref

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCloseEvent, QCursor, QFontMetrics
from PyQt5.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QToolTip, \
    QVBoxLayout

from ...app_state import app_state, get_app_state_qt
from ...bitcoin import script_template_to_string
from ...constants import ScriptType
from ...i18n import _
from ...logs import logs
from ...networks import Net, TEST_NETWORK_NAMES
from ...util import age
from ... import web
from ...wallet_database.types import PaymentRequestUpdateRow

from .amountedit import AmountEdit, BTCAmountEdit
from .qrcodewidget import QRCodeWidget
from .qrwindow import QR_Window
from .util import Buttons, ButtonsLineEdit, EnterButton, FormSectionWidget, FormSeparatorLine, \
    HelpDialogButton

if TYPE_CHECKING:
    from .main_window import ElectrumWindow
    from .receive_view import ReceiveView
    from ...wallet import AbstractAccount
    from ...wallet_database.types import KeyInstanceRow, PaymentRequestReadRow


EXPIRATION_VALUES: List[Tuple[str, Optional[int]]] = [
    (_('1 hour'), 60*60),
    (_('1 day'), 24*60*60),
    (_('1 week'), 7*24*60*60),
    (_('Never'), None)
]

if Net.NAME in TEST_NETWORK_NAMES:
    EXPIRATION_VALUES = [
        (_('1 minute'), 1*60),
        (_('2 minutes'), 2*60),
        (_('5 minutes'), 5*60),

        *EXPIRATION_VALUES,
    ]


class ReceiveDialog(QDialog):
    """
    Display a popup window with a form containing the details of an existing expected payment.
    """
    _qr_window: Optional[QR_Window] = None
    _fiat_receive_e: AmountEdit
    _receive_amount_e: BTCAmountEdit

    def __init__(self, main_window: 'ElectrumWindow', view: "ReceiveView", account_id: int,
            request_id: int) -> None:
        super().__init__(main_window)
        self.setWindowTitle(_("Expected payment"))

        # If we do not set this, this dialog does not get garbage collected and `main_window`
        # appears in `gc.get_referrers(self)` as a direct reference. So a `QDialog` merely having a
        # parent stored at the Qt level can create a circular reference, apparently. With this set,
        # the dialog will be gc'd on the next `collect` call.
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._view: Optional["ReceiveView"] = view
        self._main_window = weakref.proxy(main_window)
        self._account_id = account_id
        self._account = cast("AbstractAccount", main_window._wallet.get_account(account_id))
        self._request_id = request_id

        self._logger = logs.get_logger(f"receive-dialog[{self._account_id},{self._request_id}]")

        wallet = self._account.get_wallet()
        self._request_row = cast("PaymentRequestReadRow",
            wallet.data.read_payment_request(request_id=self._request_id))
        self._key_data = cast("KeyInstanceRow",
            wallet.data.read_keyinstance(keyinstance_id=self._request_row.keyinstance_id))

        self._layout_pending = True
        self.setLayout(self._create_form_layout())
        self._connect_widgets()
        self._layout_pending = False

        self._on_fiat_ccy_changed()
        self.update_destination()
        self._receive_amount_e.setAmount(self._request_row.requested_value)

        app_state.app_qt.fiat_ccy_changed.connect(self._on_fiat_ccy_changed)
        self._main_window.new_fx_quotes_signal.connect(self._on_ui_exchange_rate_quotes)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._view = None
        if self._qr_window is not None:
            self._qr_window.close()
            self._qr_window = None
        self._main_window.new_fx_quotes_signal.disconnect(self._on_ui_exchange_rate_quotes)
        app_state.app_qt.fiat_ccy_changed.disconnect(self._on_fiat_ccy_changed)
        super().closeEvent(event)

    def clean_up(self) -> None:
        pass

    def _on_click_button_close(self) -> None:
        self.close()

    def _on_fiat_ccy_changed(self) -> None:
        flag = bool(app_state.fx and app_state.fx.is_enabled())
        self._fiat_receive_e.setVisible(flag)

    def _on_ui_exchange_rate_quotes(self) -> None:
        edit = (self._fiat_receive_e if self._fiat_receive_e.is_last_edited
            else self._receive_amount_e)
        edit.textEdited.emit(edit.text())

    def _create_form_layout(self) -> QVBoxLayout:
        self._form = form = FormSectionWidget()

        form.add_row(_("Account"), QLabel(self._account.get_name()))

        # Really we want to display a whole standard address.
        token_address = "mqrJ2AAzrR6U3L4Nzt9zDNxuLXGEsnWP47"
        defaultFontMetrics = QFontMetrics(self.font())
        def fw(s: str) -> int:
            return defaultFontMetrics.boundingRect(s).width() + 40

        self._receive_destination_e = ButtonsLineEdit()
        self._receive_destination_e.setMinimumWidth(fw(token_address))
        self._receive_destination_e.addCopyButton()
        self._receive_destination_e.setReadOnly(True)
        self._receive_destination_e.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        form.add_row(_('Payment destination'), self._receive_destination_e)

        self._receive_message_e = QLineEdit()
        form.add_row(_('Description'), self._receive_message_e)
        self._receive_message_e.setText("" if self._request_row.description is None
            else self._request_row.description)

        self._receive_amount_e = BTCAmountEdit()
        self._fiat_receive_e = AmountEdit(app_state.fx.get_currency if app_state.fx else lambda: '')
        self._main_window.connect_fields(self._receive_amount_e, self._fiat_receive_e)

        amount_widget_layout = QHBoxLayout()
        amount_widget_layout.addWidget(self._receive_amount_e)
        amount_widget_layout.addSpacing(10)
        amount_widget_layout.addWidget(self._fiat_receive_e)
        form.add_row(_('Requested amount'), amount_widget_layout)

        self._expires_combo = QComboBox()
        self._expires_combo.addItems([i[0] for i in EXPIRATION_VALUES])
        # Default the current index to one hour or the last entry if that cannot be found for some
        # reason.
        current_index = 0
        for current_index, expiration_entry in enumerate(EXPIRATION_VALUES):
            if expiration_entry[1] == 60*60:
                break
        self._expires_combo.setCurrentIndex(current_index)
        self._expires_combo.setFixedWidth(self._receive_amount_e.width())
        self._expires_combo.hide()
        expires_text = age(self._request_row.date_created +
            self._request_row.expiration).capitalize() \
                if self._request_row.expiration else _('Never')
        self._expires_label = QLabel(expires_text)
        expires_widget_layout = QHBoxLayout()
        expires_widget_layout.addWidget(self._expires_combo)
        expires_widget_layout.addWidget(self._expires_label)
        form.add_row(_('Request expires'), expires_widget_layout)

        self._copy_link_button = EnterButton(_('Copy payment link'), self._copy_qr_data)
        self._help_button = HelpDialogButton(self, "misc", "receive-dialog", _("Help"))
        self._update_button = EnterButton(_('Update'), self._on_update_button_clicked)
        self._close_button = EnterButton(_('Close'), self._on_click_button_close)

        buttons = Buttons(self._update_button, self._close_button)
        buttons.add_left_button(self._help_button)

        self._receive_qr = QRCodeWidget(fixedSize=200)
        self._receive_qr_layout = QVBoxLayout()
        self._receive_qr_layout.addWidget(self._receive_qr)
        self._receive_qr_layout.addWidget(self._copy_link_button)

        form_vbox = QVBoxLayout()
        form_vbox.addWidget(form)
        form_vbox.addStretch(1)

        hbox = QHBoxLayout()
        hbox.addLayout(form_vbox)
        hbox.addLayout(self._receive_qr_layout)

        buttons_line = FormSeparatorLine()

        vbox = QVBoxLayout()
        vbox.addLayout(hbox)
        vbox.addWidget(buttons_line)
        vbox.addLayout(buttons)
        return vbox

    def _connect_widgets(self) -> None:
        self._receive_destination_e.textChanged.connect(self._update_receive_qr)
        self._receive_message_e.textChanged.connect(self._update_receive_qr)
        self._receive_amount_e.textChanged.connect(self._update_receive_qr)
        self._receive_qr.mouse_release_signal.connect(self._toggle_qr_window)

    def _copy_qr_data(self) -> None:
        text = self._receive_qr.data
        if text:
            get_app_state_qt().app_qt.clipboard().setText(text)
            tooltip_text = _("Text copied to clipboard")
        else:
            tooltip_text = _("Nothing to copy")
        QToolTip.showText(QCursor.pos(), tooltip_text, self._copy_link_button)

    def update_widgets(self) -> None:
        # This is currently unused, but is called in the generic `update_tabs` call in the
        # wallet window code.
        pass

    def update_destination(self) -> None:
        script_type = self._account.get_default_script_type()
        self.update_script_type(script_type)

    def update_script_type(self, script_type: ScriptType) -> None:
        """
        Update the payment destination field.

        This is called both locally, and from the account information dialog when the script type
        is changed.
        """
        text = ""
        script_template = self._account.get_script_template_for_derivation(
            script_type,
            self._key_data.derivation_type, self._key_data.derivation_data2)
        if script_template is not None:
            text = script_template_to_string(script_template)
        self._receive_destination_e.setText(text)

    # Bound to text fields in `_create_receive_form_layout`.
    def _update_receive_qr(self) -> None:
        if self._layout_pending:
            return

        amount = self._receive_amount_e.get_amount()
        message = self._receive_message_e.text()
        self._update_button.setEnabled((amount is not None) or (message != ""))

        script_template = self._account.get_script_template_for_derivation(
            self._account.get_default_script_type(),
            self._key_data.derivation_type, self._key_data.derivation_data2)
        address_text = script_template_to_string(script_template)

        uri = web.create_URI(address_text, amount, message)
        self._receive_qr.setData(uri)
        if self._qr_window and self._qr_window.isVisible():
            self._qr_window.set_content(self._receive_destination_e.text(), amount,
                                       message, uri)

    def _toggle_qr_window(self) -> None:
        if not self._qr_window:
            self._qr_window = QR_Window(self)
            self._qr_window.setVisible(True)
            self._qr_window_geometry = self._qr_window.geometry()
        else:
            if not self._qr_window.isVisible():
                self._qr_window.setVisible(True)
                self._qr_window.setGeometry(self._qr_window_geometry)
            else:
                self._qr_window_geometry = self._qr_window.geometry()
                self._qr_window.setVisible(False)

        self._update_receive_qr()

    def get_request_id(self) -> int:
        return self._request_id

    def get_bsv_edits(self) -> List[BTCAmountEdit]:
        return [ self._receive_amount_e ]

    def _on_update_button_clicked(self) -> None:
        """
        The user clicked the "Update" button.
        """
        # These are the same constraints imposed in the receive view.
        message = self._receive_message_e.text()
        if not message:
            self._main_window.show_error(_('A description is required'))
            return

        amount = self._receive_amount_e.get_amount()
        if not amount:
            amount = None

        def callback(future: concurrent.futures.Future[None]) -> None:
            # Skip if the operation was cancelled.
            if future.cancelled():
                return
            # Raise any exception if it errored or get the result if completed successfully.
            future.result()

            # NOTE This callback will be happening in the database thread. No UI calls should
            #   be made, unless we emit a signal to do it.
            def ui_callback(args: Tuple[Any, ...]) -> None:
                assert self._view is not None
                self._view.update_request_list()
                self.close()
            self._main_window.ui_callback_signal.emit(ui_callback, ())

        wallet = self._account.get_wallet()
        i = self._expires_combo.currentIndex()
        expiration = [x[1] for x in EXPIRATION_VALUES][i]

        # Expiration is just a label, so we don't use the value.
        entries = [ PaymentRequestUpdateRow(self._request_row.state, amount,
            self._request_row.expiration, message, self._request_row.paymentrequest_id) ]
        future = wallet.data.update_payment_requests(entries)
        future.add_done_callback(callback)

        self._update_button.setEnabled(False)
