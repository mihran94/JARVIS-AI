"""Read visible text from one user-selected Windows camera frame."""
from shutil import which

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QProcess, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from security.policy import Action, Stopped


def open_camera_reader(window):
    ticket = window.policy.ticket()
    if not window.confirm(Action('Start camera preview', 'Selected local camera')):
        return
    window.policy.check(ticket)

    from PySide6.QtMultimedia import QCamera, QMediaCaptureSession, QMediaDevices
    from PySide6.QtMultimediaWidgets import QVideoWidget

    executable = which("tesseract")
    devices = QMediaDevices.videoInputs()
    if not devices:
        raise ValueError("No webcam found. Connect your webcam and check Windows camera permissions.")

    dialog = QDialog(window)
    dialog.setWindowTitle("Connected camera")
    dialog.resize(690, 660)
    layout = QVBoxLayout(dialog)
    choice = QComboBox()
    choice.addItems([item.description() for item in devices])
    layout.addWidget(choice)
    video = QVideoWidget()
    video.setMinimumHeight(260)
    layout.addWidget(video, 1)
    still = QLabel()
    still.setAlignment(Qt.AlignmentFlag.AlignCenter)
    still.hide()
    layout.addWidget(still, 1)
    row = QHBoxLayout()
    capture = QPushButton("Capture frame")
    retake = QPushButton("Retake")
    read = QPushButton("Read text")
    language = QComboBox()
    language.addItem("English", "eng")
    language.addItem("Tamil + English", "tam+eng")
    language.addItem("French", "fra")
    for widget in (capture, retake, language, read):
        row.addWidget(widget)
    layout.addLayout(row)
    status = QLabel("Capture the text, review the frame, then select Read text.")
    status.setWordWrap(True)
    layout.addWidget(status)
    result = QPlainTextEdit()
    result.setReadOnly(True)
    result.setPlaceholderText("Recognized text appears here. Select it to copy.")
    layout.addWidget(result)
    search_row = QHBoxLayout()
    query = QLineEdit()
    query.setPlaceholderText("Find a word in the recognized text")
    find = QPushButton("Find next")
    search_row.addWidget(query, 1)
    search_row.addWidget(find)
    layout.addLayout(search_row)
    retake.setEnabled(False)
    read.setEnabled(False)

    session = QMediaCaptureSession(dialog)
    session.setVideoOutput(video)
    process = QProcess(dialog)
    timeout = QTimer(dialog)
    timeout.setSingleShot(True)
    camera = None
    image = None
    pending_frame = None

    def start_camera():
        nonlocal camera, image
        image = None
        if camera is not None:
            camera.stop()
            camera.deleteLater()
        camera = QCamera(devices[choice.currentIndex()], dialog)
        camera.errorOccurred.connect(
            lambda error, message: status.setText("Camera unavailable: " + message))
        session.setCamera(camera)
        still.hide()
        video.show()
        read.setEnabled(False)
        retake.setEnabled(False)
        capture.setEnabled(True)
        result.clear()
        status.setText("Hold the text steady in the preview, then capture.")
        camera.start()

    def freeze():
        nonlocal image
        frame = video.videoSink().videoFrame()
        image = frame.toImage()
        if image.isNull():
            status.setText("Wait for your camera preview, then try again.")
            return
        camera.stop()
        still.setPixmap(QPixmap.fromImage(image).scaled(
            video.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        video.hide()
        still.show()
        capture.setEnabled(False)
        read.setEnabled(True)
        retake.setEnabled(True)
        status.setText("Review the captured frame and choose the reading language.")

    def recognize():
        try:
            window.policy.check(ticket)
        except Stopped:
            dialog.reject()
            return
        nonlocal pending_frame
        if image is None or image.isNull() or process.state() != QProcess.ProcessState.NotRunning:
            return
        if not executable:
            status.setText("To read text, install Tesseract OCR, add it to PATH, and restart JARVIS.")
            return
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer, "PNG"):
            status.setText("Camera frame could not be prepared.")
            return
        buffer.close()
        result.clear()
        for widget in (read, retake, choice, language):
            widget.setEnabled(False)
        status.setText("Reading text locally…")
        pending_frame = data
        timeout.start(30000)
        process.start(executable, ["stdin", "stdout", "-l", language.currentData()])

    def send_frame():
        if pending_frame is not None:
            process.write(pending_frame)
        process.closeWriteChannel()

    def restore_controls():
        nonlocal pending_frame
        pending_frame = None
        timeout.stop()
        for widget in (read, retake, choice, language):
            widget.setEnabled(True)

    def finished(code, exit_status):
        restore_controls()
        if code != 0 or exit_status != QProcess.ExitStatus.NormalExit:
            status.setText("OCR did not finish. Check that the selected Tesseract language files are installed.")
            return
        text = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace").strip()
        result.setPlainText(text)
        status.setText("Text ready. Check it against the photo." if text else "No text found. Retake with better lighting.")

    def failed(error):
        if error == QProcess.ProcessError.FailedToStart:
            restore_controls()
            status.setText("Could not start Tesseract OCR.")

    def find_word():
        from PySide6.QtGui import QTextCursor

        term = query.text().strip()
        if not term:
            return
        if not result.find(term):
            result.moveCursor(QTextCursor.MoveOperation.Start)
            if not result.find(term):
                status.setText("No match in the recognized text.")
                return
        status.setText("Match selected in the recognized text.")

    def check_stop():
        try:
            window.policy.check(ticket)
        except Stopped:
            dialog.reject()

    guard = QTimer(dialog)
    guard.timeout.connect(check_stop)
    guard.start(250)
    timeout.timeout.connect(process.kill)
    choice.currentIndexChanged.connect(start_camera)
    retake.clicked.connect(start_camera)
    capture.clicked.connect(freeze)
    read.clicked.connect(recognize)
    find.clicked.connect(find_word)
    query.returnPressed.connect(find_word)
    process.finished.connect(finished)
    process.started.connect(send_frame)
    process.errorOccurred.connect(failed)
    start_camera()
    try:
        dialog.exec()
    finally:
        camera.stop()
        if process.state() != QProcess.ProcessState.NotRunning:
            process.kill()
            process.waitForFinished(1000)
        dialog.deleteLater()
