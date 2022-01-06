# Open BSV License version 4
#
# Copyright (c) 2021,2022 Bitcoin Association for BSV ("Bitcoin Association")
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# 1 - The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# 2 - The Software, and any software that is derived from the Software or parts thereof,
# can only be used on the Bitcoin SV blockchains. The Bitcoin SV blockchains are defined,
# for purposes of this license, as the Bitcoin blockchain containing block height #556767
# with the hash "000000000000000001d956714215d96ffc00e0afda4cd0a96c96f8d802b1662b" and
# that contains the longest persistent chain of blocks accepted by this Software and which
# are valid under the rules set forth in the Bitcoin white paper (S. Nakamoto, Bitcoin: A
# Peer-to-Peer Electronic Cash System, posted online October 2008) and the latest version
# of this Software available in this repository or another repository designated by Bitcoin
# Association, as well as the test blockchains that contain the longest persistent chains
# of blocks accepted by this Software and which are valid under the rules set forth in the
# Bitcoin whitepaper (S. Nakamoto, Bitcoin: A Peer-to-Peer Electronic Cash System, posted
# online October 2008) and the latest version of this Software available in this repository,
# or another repository designated by Bitcoin Association
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.


from PyQt5.QtCore import QUrl
from PyQt5.QtWidgets import QTextBrowser, QVBoxLayout, QWidget

from electrumsv.i18n import _
from electrumsv.util import text_resource_path

from .util import Buttons, OkButton, WindowModalDialog


class HelpDialog(WindowModalDialog):
    def __init__(self, parent: QWidget, help_dirname: str, help_file_name: str) -> None:
        super().__init__(parent)

        self.setWindowTitle(_("ElectrumSV - In-Wallet Help"))
        self.setMinimumSize(450, 400)

        source_path = text_resource_path(help_dirname, f"{help_file_name}.html")

        widget = QTextBrowser()
        widget.document().setDocumentMargin(15)
        widget.setOpenLinks(True)
        widget.setOpenExternalLinks(True)
        widget.setAcceptRichText(True)
        widget.setSource(QUrl.fromLocalFile(source_path))

        vbox = QVBoxLayout(self)
        vbox.addWidget(widget)
        vbox.addLayout(Buttons(OkButton(self)))

    def run(self) -> int:
        return self.exec_()
