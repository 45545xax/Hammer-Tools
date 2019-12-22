from __future__ import print_function

import os
import sqlite3

try:
    from PyQt5.QtWidgets import *
    from PyQt5.QtGui import *
    from PyQt5.QtCore import *

    Signal = pyqtSignal
except ImportError:
    from PySide2.QtWidgets import *
    from PySide2.QtGui import *
    from PySide2.QtCore import *

import hou

from .quick_selection import FilterField
from .utils import fuzzyMatch


def createDatabase(filepath):
    db = sqlite3.connect(filepath)

    cursor = db.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS `folder` ('
                   '`id` INTEGER PRIMARY KEY,'
                   '`path` TEXT UNIQUE);')
    cursor.execute('CREATE TABLE IF NOT EXISTS `file` ('
                   '`id` INTEGER PRIMARY KEY,'
                   '`folder_id` INTEGER NOT NULL,'
                   '`name` TEXT NOT NULL,'
                   '`extension` TEXT NOT NULL);')
    cursor.execute('CREATE TABLE IF NOT EXISTS `log` ('
                   '`id` INTEGER PRIMARY KEY,'
                   '`file_id` INTEGER,'
                   '`event` INTEGER,'
                   '`timestamp` INTEGER);')
    db.commit()

    return db


class SessionWatcher:
    class EventType:
        Load = 0
        Save = 1

    def __init__(self):
        # Database
        db_file = os.path.abspath(os.path.join(hou.homeHoudiniDirectory(), 'hammer_previous_files.db'))
        if not os.path.exists(db_file):
            self.db = createDatabase(db_file)
        else:
            self.db = sqlite3.connect(db_file)

    def logEvent(self, filepath, event):
        query = self.db.cursor()
        location, fullname = os.path.split(filepath)
        name, extension = os.path.splitext(fullname)
        # Check folder and get id
        r = query.execute('SELECT `id` FROM `folder` WHERE `path` == ? LIMIT 1;', (location,))
        r = r.fetchone()
        if r is None:
            query.execute('INSERT INTO `folder` (`path`) VALUES (?);', (location,))
            self.db.commit()
            rowid = query.lastrowid
        else:
            rowid = r[0]
        # Check file and get id
        r = query.execute('SELECT `id` FROM `file` WHERE `folder_id` == ? AND `name` == ? AND `extension` == ? LIMIT 1;',
                          (rowid, name, extension))
        r = r.fetchone()
        if r is None:
            query.execute('INSERT INTO `file` (`folder_id`, `name`, `extension`) VALUES (?, ?, ?);',
                          (rowid, name, extension))
            self.db.commit()
            rowid = query.lastrowid
        else:
            rowid = r[0]
        # Add event to log
        query.execute('INSERT INTO `log` (`file_id`, `event`, `timestamp`) VALUES (?, ?, datetime("now", "localtime"));',
                      (rowid, event))
        self.db.commit()

    def __call__(self, event_type):
        if event_type == hou.hipFileEventType.AfterLoad:
            self.logEvent(hou.hipFile.path(), SessionWatcher.EventType.Load)
        elif event_type == hou.hipFileEventType.BeforeSave:
            self.logEvent(hou.hipFile.path(), SessionWatcher.EventType.Save)


def setSessionWatcher():
    hou.session.hammer_session_watcher = SessionWatcher()
    hou.hipFile.addEventCallback(hou.session.hammer_session_watcher)


class FuzzyFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super(FuzzyFilterProxyModel, self).__init__(parent)

        self.__filter_pattern = ''
        self.setDynamicSortFilter(True)

    def setFilterPattern(self, pattern):
        self.beginResetModel()
        if self.filterCaseSensitivity() == Qt.CaseInsensitive:
            self.__filter_pattern = pattern.lower()
        else:
            self.__filter_pattern = pattern
        self.endResetModel()

    def filterAcceptsRow(self, source_row, source_parent):
        source_model = self.sourceModel()
        text = source_model.data(source_model.index(source_row, 1, source_parent), Qt.UserRole)
        matches, weight = fuzzyMatch(self.__filter_pattern, text if self.filterCaseSensitivity() == Qt.CaseSensitive else text.lower())
        return matches

    def lessThan(self, source_left, source_right):
        text1 = source_left.data(Qt.DisplayRole)
        _, weight1 = fuzzyMatch(self.__filter_pattern, text1 if self.filterCaseSensitivity() == Qt.CaseSensitive else text1.lower())

        text2 = source_right.data(Qt.DisplayRole)
        _, weight2 = fuzzyMatch(self.__filter_pattern, text2 if self.filterCaseSensitivity() == Qt.CaseSensitive else text2.lower())

        return weight1 < weight2


class PreviousFilesModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super(PreviousFilesModel, self).__init__(parent)

        # Icons
        self.__file_exists_icon = hou.qt.Icon('TOP_status_cooked', 20, 20)
        self.__file_not_exists_icon = hou.qt.Icon('TOP_status_error', 20, 20)

        # Database
        db_file = os.path.abspath(os.path.join(hou.homeHoudiniDirectory(), 'hammer_previous_files.db'))
        if not os.path.exists(db_file):
            self.db = createDatabase(db_file)
        else:
            self.db = sqlite3.connect(db_file)

        self.__log = (())

        self.updateLogData()

    def updateLogData(self):
        self.beginResetModel()
        self.__log = self.db.cursor().execute('SELECT file.name, folder.path, log.timestamp, file.extension FROM `log` '
                                              'JOIN `file` ON log.file_id = file.id '
                                              'JOIN `folder` ON file.folder_id = folder.id '
                                              'GROUP BY log.file_id '
                                              'ORDER BY log.id DESC;').fetchall()
        self.endResetModel()

    def rowCount(self, parent):
        return len(self.__log)

    def columnCount(self, parent):
        return 3

    def headerData(self, section, orientation, role):
        headers = ('Name', 'Location', 'Timestamp')
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return headers[section]

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def data(self, index, role):
        if role == Qt.DisplayRole:
            return self.__log[index.row()][index.column()]
        elif role == Qt.UserRole:
            if index.column() == 0:
                return self.__log[index.row()][3]
            if index.column() == 1:
                row = index.row()
                name, location, _, extension = self.__log[row]
                return os.path.normpath(os.path.join(location, name + extension)).replace('\\', '/')
        elif role == Qt.DecorationRole:
            if index.column() == 0:
                name, location, _, extension = self.__log[index.row()]
                if os.path.exists(os.path.join(location, name + extension)):
                    return self.__file_exists_icon
                else:
                    return self.__file_not_exists_icon


class PreviousFilesView(QTableView):
    def __init__(self):
        super(PreviousFilesView, self).__init__()

        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().hide()
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)


def openTemp():
    os.startfile(hou.getenv('TEMP'))


def importFBX(path, suppress_save_prompt=False):
    hou.hipFile.importFBX(file_name=path, suppress_save_prompt=suppress_save_prompt)


def importAlembic(path):
    location, file = os.path.split(path)
    name, extension = os.path.splitext(file)
    obj_node = hou.node('/obj')
    alembic_node = obj_node.createNode('alembicarchive', name)
    alembic_node.parm('fileName').set(path)
    alembic_node.parm('buildHierarchy').pressButton()


def importGLTF(path):
    location, file = os.path.split(path)
    name, extension = os.path.splitext(file)
    obj_node = hou.node('/obj')
    gltf_node = obj_node.createNode('gltf_hierarchy', name)
    gltf_node.parm('filename').set(path)
    gltf_node.parm('lockgeo').set(0)
    if extension.lower() == '.glb':
        gltf_node.parm('assetfolder').set('$HIP/{}_data'.format(name))
    gltf_node.parm('buildscene').pressButton()


class PreviousFiles(QDialog):
    def __init__(self, parent=None):
        super(PreviousFiles, self).__init__(parent, Qt.Window)

        self.setWindowTitle('Previous Files')
        self.resize(800, 500)
        self.setStyleSheet(hou.qt.styleSheet())

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        left_vertical_layout = QVBoxLayout()
        left_vertical_layout.setContentsMargins(0, 0, 0, 0)
        left_vertical_layout.setSpacing(0)
        main_layout.addLayout(left_vertical_layout)

        self.new = QPushButton('New File')
        self.new.setMinimumWidth(100)
        self.new.clicked.connect(self.createNewHip)
        left_vertical_layout.addWidget(self.new)

        self.open_button_menu = QMenu(self)
        open_in_manual_mode = QAction('Open in Manual Mode', self)
        open_in_manual_mode.triggered.connect(lambda: self.chooseAndOpenFile(True))
        self.open_button_menu.addAction(open_in_manual_mode)

        self.open_button = QToolButton()
        self.open_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.open_button.setMenu(self.open_button_menu)
        self.open_button.setStyleSheet('border-radius: 1; border-style: none')
        self.open_button.setMinimumWidth(100)
        self.open_button.setText('Open...')
        self.open_button.clicked.connect(self.chooseAndOpenFile)
        left_vertical_layout.addWidget(self.open_button)

        self.merge_button = QPushButton('Merge...')
        self.merge_button.clicked.connect(self.mergeFiles)
        left_vertical_layout.addWidget(self.merge_button)

        spacer = QSpacerItem(0, 0, QSizePolicy.Ignored, QSizePolicy.Expanding)
        left_vertical_layout.addSpacerItem(spacer)

        self.open_temp_button = QPushButton('Open Temp')
        self.open_temp_button.setToolTip('Open Houdini Temp Location')
        self.open_temp_button.clicked.connect(openTemp)
        left_vertical_layout.addWidget(self.open_temp_button)

        self.open_crash_button_menu = QMenu(self)
        open_crash_in_manual_mode = QAction('Open in Manual Mode', self)
        open_crash_in_manual_mode.triggered.connect(lambda: self.openLastCrashFile(True))
        self.open_crash_button_menu.addAction(open_crash_in_manual_mode)
        # Todo: repair crash file action
        # Todo: remove crash files action

        self.open_crash_button = QToolButton()
        self.open_crash_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.open_crash_button.setMenu(self.open_crash_button_menu)
        self.open_crash_button.setStyleSheet('border-radius: 1; border-style: none; background-color: rgb(165, 70, 70);')
        self.open_crash_button.setMinimumWidth(100)
        self.open_crash_button.setText('Open Crash')
        self.open_crash_button.setToolTip('Open Last Crash File')
        self.open_crash_button.clicked.connect(self.openLastCrashFile)
        left_vertical_layout.addWidget(self.open_crash_button)

        right_vertical_layout = QVBoxLayout()
        right_vertical_layout.setContentsMargins(0, 0, 0, 0)
        right_vertical_layout.setSpacing(0)
        main_layout.addLayout(right_vertical_layout)

        # Filter
        self.filter_field = FilterField()
        right_vertical_layout.addWidget(self.filter_field)

        # File list
        self.model = PreviousFilesModel(self)

        self.filter_model = FuzzyFilterProxyModel(self)
        self.filter_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.filter_model.setSourceModel(self.model)

        self.view = PreviousFilesView()
        self.view.setModel(self.filter_model)
        self.view.setSortingEnabled(True)
        self.view.sortByColumn(0, Qt.DescendingOrder)
        self.view.doubleClicked.connect(lambda: self.openSelectedFile())
        right_vertical_layout.addWidget(self.view)

        self.filter_field.textChanged.connect(self.filter_model.setFilterPattern)

        # File list menu
        self.menu = QMenu()

        self.open_selected_file_action = QAction('Open', self)
        self.open_selected_file_action.triggered.connect(lambda: self.openSelectedFile())
        self.menu.addAction(self.open_selected_file_action)

        self.open_selected_file_in_manual_mode_action = QAction('Open in Manual Mode', self)
        self.open_selected_file_in_manual_mode_action.triggered.connect(lambda: self.openSelectedFile(True))
        self.menu.addAction(self.open_selected_file_in_manual_mode_action)

        self.merge_selected_files_action = QAction('Merge', self)
        self.merge_selected_files_action.triggered.connect(self.mergeSelectedFiles)
        self.menu.addAction(self.merge_selected_files_action)

        self.open_selected_locations_action = QAction('Open Location', self)
        self.open_selected_locations_action.triggered.connect(self.openSelectedLocations)
        self.menu.addAction(self.open_selected_locations_action)

        self.menu.addSeparator()

        self.filter_by_name_action = QAction('Filter by Name', self)
        self.filter_by_name_action.triggered.connect(self.filterByName)
        self.menu.addAction(self.filter_by_name_action)

        self.filter_by_location_action = QAction('Filter by Location', self)
        self.filter_by_location_action.triggered.connect(self.filterByLocation)
        self.menu.addAction(self.filter_by_location_action)

        self.menu.addSeparator()

        self.copy_name_action = QAction('Copy Name', self)
        self.copy_name_action.triggered.connect(self.copySelectedNames)
        self.menu.addAction(self.copy_name_action)

        self.copy_location_action = QAction('Copy Location', self)
        self.copy_location_action.triggered.connect(self.copySelectedLocations)
        self.menu.addAction(self.copy_location_action)

        self.copy_link_action = QAction('Copy Link', self)
        self.copy_link_action.triggered.connect(self.copySelectedLinks)
        self.menu.addAction(self.copy_link_action)

        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.showMenu)

        # Actions
        refresh_action = QAction('Refresh', self)
        refresh_action.setShortcut(QKeySequence(Qt.Key_F5))
        refresh_action.triggered.connect(self.model.updateLogData)
        self.addAction(refresh_action)

    def showMenu(self):
        selection_model = self.view.selectionModel()
        selected_row_count = len(selection_model.selectedRows())
        if selected_row_count > 0:
            if selected_row_count > 1:
                self.open_selected_file_action.setEnabled(False)
                self.open_selected_file_in_manual_mode_action.setEnabled(False)
                self.filter_by_name_action.setEnabled(False)
                self.filter_by_location_action.setEnabled(False)
            else:  # Single file
                self.open_selected_file_action.setEnabled(True)
                self.open_selected_file_in_manual_mode_action.setEnabled(True)
                self.filter_by_name_action.setEnabled(True)
                self.filter_by_location_action.setEnabled(True)
            self.menu.exec_(QCursor.pos())

    def openSelectedFile(self, manual=False):
        self.hide()
        selection = self.view.selectionModel()
        location = selection.selectedRows(1)[0].data(Qt.DisplayRole)
        name = selection.selectedRows(0)[0].data(Qt.DisplayRole)
        extension = selection.selectedRows(0)[0].data(Qt.UserRole)
        self.openFile('{}/{}{}'.format(location, name, extension), manual)

    def mergeSelectedFiles(self):
        self.hide()
        selection = self.view.selectionModel()
        # todo
        locations = map(lambda index: index.data(Qt.DisplayRole), selection.selectedRows(1))
        names = map(lambda index: index.data(Qt.DisplayRole), selection.selectedRows(0))
        extensions = map(lambda index: index.data(Qt.UserRole), selection.selectedRows(0))
        for location, name, extension in zip(locations, names, extensions):
            hou.hipFile.merge('{}/{}{}'.format(location, name, extension))

    def openSelectedLocations(self):
        selection = self.view.selectionModel()
        if len(selection.selectedRows()) > 4:
            return
        for index in selection.selectedRows(1):
            os.startfile(index.data(Qt.DisplayRole))

    def createNewHip(self):
        self.hide()
        hou.hipFile.clear()

    def openFile(self, file, manual=False):
        file = hou.expandString(file)
        _, extension = os.path.splitext(file)
        try:
            if extension.lower().startswith('.hip'):
                hou.hipFile.load(file)
            else:
                hou.hipFile.clear(suppress_save_prompt=True)
                if extension.lower() == '.abc':
                    importAlembic(file)
                elif extension.lower() == '.fbx':
                    importFBX(file)
                elif extension.lower().startswith('.gl'):
                    importGLTF(file)
                hou.session.hammer_session_watcher.logEvent(file, SessionWatcher.EventType.Load)
            if manual:
                hou.setUpdateMode(hou.updateMode.Manual)
            self.hide()
        except hou.OperationFailed:
            self.show()

    def chooseAndOpenFile(self, manual=False):
        files = hou.ui.selectFile(title='Open', pattern='*.hip, *.hipnc, *.hiplc, *.hip*, *.abc, *.fbx, *.gltf, *.glb', chooser_mode=hou.fileChooserMode.Read).split(' ; ')
        if files and files[0]:
            self.openFile(files[0], manual)

    def mergeFiles(self):
        files = hou.ui.selectFile(title='Merge', file_type=hou.fileType.Hip, multiple_select=True, chooser_mode=hou.fileChooserMode.Read).split(' ; ')
        if files and files[0]:
            files = [hou.expandString(file) for file in files]  # Prevent aging variables
            for file in files:
                hou.hipFile.merge(file)
            self.hide()

    def detectCrashFile(self):
        temp_path = hou.getenv('TEMP')
        for file in os.listdir(temp_path):
            if file.startswith('crash.') and file.endswith('.hip') or file.endswith('.hiplc') or file.endswith('.hipnc'):
                self.open_crash_button.setVisible(True)
                return
        self.open_crash_button.setVisible(False)

    def openLastCrashFile(self, manual=False):
        last_file = None
        last_timestamp = 0
        houdini_temp_path = hou.getenv('TEMP')
        for file in os.listdir(houdini_temp_path):
            if file.startswith('crash.') and file.endswith('.hip') or file.endswith('.hiplc') or file.endswith('.hipnc'):
                timestamp = os.stat('{}/{}'.format(houdini_temp_path, file)).st_mtime
                if timestamp > last_timestamp:
                    last_timestamp = timestamp
                    last_file = file
        if last_file is None:
            hou.ui.displayMessage('Crash file not found')
            self.detectCrashFile()
        else:
            self.hide()
            hou.hipFile.load('{}/{}'.format(houdini_temp_path, last_file))
            if manual:
                hou.setUpdateMode(hou.updateMode.Manual)

    def filterByName(self):
        selection = self.view.selectionModel()
        name = selection.selectedRows(0)[0].data(Qt.DisplayRole)
        self.filter_field.setText(name)

    def filterByLocation(self):
        selection = self.view.selectionModel()
        location = selection.selectedRows(1)[0].data(Qt.DisplayRole)
        self.filter_field.setText(location)

    def copySelectedNames(self):
        selection = self.view.selectionModel()
        names = []
        for index in selection.selectedRows(0):
            names.append(index.data(Qt.DisplayRole))
        qApp.clipboard().setText('\n'.join(names))

    def copySelectedLocations(self):
        selection = self.view.selectionModel()
        locations = []
        for index in selection.selectedRows(1):
            locations.append(index.data(Qt.DisplayRole))
        qApp.clipboard().setText('\n'.join(locations))

    def copySelectedLinks(self):
        selection = self.view.selectionModel()
        links = []
        for index in selection.selectedRows(1):
            links.append(index.data(Qt.UserRole))
        qApp.clipboard().setText('\n'.join(links))

    def showEvent(self, event):
        self.model.updateLogData()
        self.detectCrashFile()
        self.filter_field.setFocus()
        self.filter_field.selectAll()
        super(PreviousFiles, self).showEvent(event)


def show():
    if not hasattr(hou.session, 'hammer_previous_files'):
        hou.session.hammer_previous_files = PreviousFiles(hou.qt.mainWindow())
    hou.session.hammer_previous_files.show()