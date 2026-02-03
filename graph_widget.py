"""Reusable PySide6 widget to visualize a directed graph."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QVBoxLayout,
    QWidget,
)

try:
    import networkx as nx
except ImportError:  # pragma: no cover - optional dependency
    nx = None


@dataclass
class GraphModel:
    """Simple directed graph model with styling metadata."""

    nodes: List[str] = field(default_factory=list)
    edges: List[Tuple[str, str]] = field(default_factory=list)
    node_colors: Dict[str, QColor] = field(default_factory=dict)
    edge_colors: Dict[Tuple[str, str], QColor] = field(default_factory=dict)
    edge_dotted: Dict[Tuple[str, str], bool] = field(default_factory=dict)

    def add_node(self, node_id: str) -> None:
        if node_id not in self.nodes:
            self.nodes.append(node_id)

    def add_edge(self, src_id: str, dst_id: str) -> None:
        edge = (src_id, dst_id)
        if edge not in self.edges:
            self.edges.append(edge)

    def remove_node(self, node_id: str) -> None:
        if node_id in self.nodes:
            self.nodes.remove(node_id)
        self.edges = [edge for edge in self.edges if node_id not in edge]
        self.node_colors.pop(node_id, None)
        for edge in list(self.edge_colors.keys()):
            if node_id in edge:
                self.edge_colors.pop(edge, None)
        for edge in list(self.edge_dotted.keys()):
            if node_id in edge:
                self.edge_dotted.pop(edge, None)

    def remove_edge(self, src_id: str, dst_id: str) -> None:
        edge = (src_id, dst_id)
        if edge in self.edges:
            self.edges.remove(edge)
        self.edge_colors.pop(edge, None)
        self.edge_dotted.pop(edge, None)


@dataclass
class LayoutConfig:
    node_width: float = 120.0
    node_height: float = 50.0
    horizontal_spacing: float = 180.0
    vertical_spacing: float = 120.0
    scene_padding: float = 60.0


class NodeItem(QGraphicsRectItem):
    """Graphics item representing a node."""

    def __init__(self, node_id: str, rect: QRectF, color: QColor) -> None:
        super().__init__(rect)
        self.node_id = node_id
        self.setBrush(QBrush(color))
        self.setPen(QPen(Qt.black, 1.2))
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
        self.setZValue(1)
        self._label_item = QGraphicsSimpleTextItem(node_id, self)
        self._update_label_position()

    def _update_label_position(self) -> None:
        rect = self.rect()
        label_rect = self._label_item.boundingRect()
        x = rect.center().x() - label_rect.width() / 2
        y = rect.center().y() - label_rect.height() / 2
        self._label_item.setPos(x, y)

    def set_color(self, color: QColor) -> None:
        self.setBrush(QBrush(color))

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self.scene() and hasattr(self.scene(), "node_pressed"):
            self.scene().node_pressed.emit(self.node_id)
        super().mousePressEvent(event)

    def itemChange(self, change, value):  # noqa: N802 - Qt override
        if change == QGraphicsItem.ItemPositionChange:
            if self.scene() and hasattr(self.scene(), "node_moved"):
                self.scene().node_moved.emit(self.node_id, value)
        if change == QGraphicsItem.ItemPositionHasChanged:
            if self.scene() and hasattr(self.scene(), "node_move_finished"):
                self.scene().node_move_finished.emit(self.node_id, self.pos())
        return super().itemChange(change, value)


class EdgeItem(QGraphicsPathItem):
    """Graphics item representing a directed edge."""

    def __init__(self, src_id: str, dst_id: str, color: QColor, dotted: bool) -> None:
        super().__init__()
        self.src_id = src_id
        self.dst_id = dst_id
        self._color = color
        self._dotted = dotted
        self.setZValue(0)
        self.update_pen()

    def update_pen(self) -> None:
        pen = QPen(self._color, 2.0)
        pen.setStyle(Qt.DotLine if self._dotted else Qt.SolidLine)
        self.setPen(pen)

    def set_color(self, color: QColor) -> None:
        self._color = color
        self.update_pen()

    def set_dotted(self, dotted: bool) -> None:
        self._dotted = dotted
        self.update_pen()

    def update_path(self, start: QPointF, end: QPointF) -> None:
        path = QPainterPath(start)
        mid_y = (start.y() + end.y()) / 2
        path.lineTo(start.x(), mid_y)
        path.lineTo(end.x(), mid_y)
        path.lineTo(end)
        self.setPath(path)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        path = self.path()
        if path.isEmpty():
            return
        end = path.pointAtPercent(1.0)
        angle = path.angleAtPercent(1.0)
        arrow_size = 10.0
        painter.setBrush(self.pen().color())
        painter.setPen(self.pen())
        radians = math.radians(angle - 90)
        left = QPointF(
            end.x() + arrow_size * math.cos(radians + 0.5),
            end.y() + arrow_size * math.sin(radians + 0.5),
        )
        right = QPointF(
            end.x() + arrow_size * math.cos(radians - 0.5),
            end.y() + arrow_size * math.sin(radians - 0.5),
        )
        arrow = QPainterPath()
        arrow.moveTo(end)
        arrow.lineTo(left)
        arrow.lineTo(right)
        arrow.closeSubpath()
        painter.drawPath(arrow)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self.scene() and hasattr(self.scene(), "edge_pressed"):
            self.scene().edge_pressed.emit(self.src_id, self.dst_id)
        super().mousePressEvent(event)


class GraphScene(QGraphicsScene):
    node_pressed = Signal(str)
    edge_pressed = Signal(str, str)
    node_moved = Signal(str, QPointF)
    node_move_finished = Signal(str, QPointF)


class GraphViewWidget(QWidget):
    """Reusable widget for visualizing a directed graph."""

    nodePressed = Signal(str)
    edgePressed = Signal(str, str)
    nodeApproachingBranch = Signal(str, int)
    nodeDroppedOnBranch = Signal(str, int)

    def __init__(
        self,
        nodes: Optional[Iterable[str]] = None,
        edges: Optional[Iterable[Tuple[str, str]]] = None,
        config: Optional[LayoutConfig] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._config = config or LayoutConfig()
        self._model = GraphModel(
            nodes=list(nodes or []),
            edges=list(edges or []),
        )
        self._branch_centers: List[float] = []
        self._node_items: Dict[str, NodeItem] = {}
        self._edge_items: Dict[Tuple[str, str], EdgeItem] = {}

        self._scene = GraphScene(self)
        self._view = QGraphicsView(self._scene, self)
        self._view.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self._view.setDragMode(QGraphicsView.ScrollHandDrag)

        layout = QVBoxLayout(self)
        layout.addWidget(self._view)
        layout.setContentsMargins(0, 0, 0, 0)

        self._scene.node_pressed.connect(self.nodePressed)
        self._scene.edge_pressed.connect(self.edgePressed)
        self._scene.node_moved.connect(self._handle_node_move)
        self._scene.node_move_finished.connect(self._handle_node_move_finished)

        self._rebuild_scene()

    def add_node(self, node_id: str) -> None:
        """Add a node and relayout the graph."""
        self._model.add_node(node_id)
        self._rebuild_scene()

    def add_edge(self, src_id: str, dst_id: str) -> None:
        """Add a directed edge and relayout the graph."""
        self._model.add_edge(src_id, dst_id)
        self._rebuild_scene()

    def remove_node(self, node_id: str) -> None:
        """Remove a node and relayout the graph."""
        self._model.remove_node(node_id)
        self._rebuild_scene()

    def remove_edge(self, src_id: str, dst_id: str) -> None:
        """Remove an edge and relayout the graph."""
        self._model.remove_edge(src_id, dst_id)
        self._rebuild_scene()

    def set_node_color(self, node_id: str, color: QColor | str) -> None:
        """Set node color for a given node id."""
        qcolor = QColor(color)
        self._model.node_colors[node_id] = qcolor
        item = self._node_items.get(node_id)
        if item:
            item.set_color(qcolor)

    def set_edge_color(self, src_id: str, dst_id: str, color: QColor | str) -> None:
        """Set edge color for a given edge."""
        qcolor = QColor(color)
        edge = (src_id, dst_id)
        self._model.edge_colors[edge] = qcolor
        item = self._edge_items.get(edge)
        if item:
            item.set_color(qcolor)

    def set_edge_style(self, src_id: str, dst_id: str, dotted: bool) -> None:
        """Set dotted style for a given edge."""
        edge = (src_id, dst_id)
        self._model.edge_dotted[edge] = dotted
        item = self._edge_items.get(edge)
        if item:
            item.set_dotted(dotted)

    def _handle_node_move(self, node_id: str, pos: QPointF) -> None:
        self._update_edges()
        branch_index = self._nearest_branch(pos.x())
        if branch_index is not None:
            self.nodeApproachingBranch.emit(node_id, branch_index)

    def _handle_node_move_finished(self, node_id: str, pos: QPointF) -> None:
        self._update_edges()
        branch_index = self._nearest_branch(pos.x())
        if branch_index is not None:
            self.nodeDroppedOnBranch.emit(node_id, branch_index)

    def _nearest_branch(self, x_pos: float) -> Optional[int]:
        if not self._branch_centers:
            return None
        distances = [abs(x_pos - center) for center in self._branch_centers]
        return int(distances.index(min(distances)))

    def _rebuild_scene(self) -> None:
        self._scene.clear()
        self._node_items.clear()
        self._edge_items.clear()
        positions, branch_centers = self._compute_layout()
        self._branch_centers = branch_centers
        for edge in self._model.edges:
            color = self._model.edge_colors.get(edge, QColor("#444444"))
            dotted = self._model.edge_dotted.get(edge, False)
            edge_item = EdgeItem(edge[0], edge[1], color, dotted)
            self._edge_items[edge] = edge_item
            self._scene.addItem(edge_item)
        for node_id in self._model.nodes:
            color = self._model.node_colors.get(node_id, QColor("#d9e8ff"))
            rect = QRectF(0, 0, self._config.node_width, self._config.node_height)
            node_item = NodeItem(node_id, rect, color)
            position = positions.get(node_id, QPointF(0, 0))
            node_item.setPos(position)
            self._node_items[node_id] = node_item
            self._scene.addItem(node_item)
        self._update_edges()
        self._update_scene_rect()

    def _update_edges(self) -> None:
        for (src_id, dst_id), edge_item in self._edge_items.items():
            src_item = self._node_items.get(src_id)
            dst_item = self._node_items.get(dst_id)
            if not src_item or not dst_item:
                continue
            start = src_item.sceneBoundingRect().center()
            end = dst_item.sceneBoundingRect().center()
            edge_item.update_path(start, end)

    def _update_scene_rect(self) -> None:
        items_rect = self._scene.itemsBoundingRect()
        padding = self._config.scene_padding
        self._scene.setSceneRect(items_rect.adjusted(-padding, -padding, padding, padding))

    def _compute_layout(self) -> Tuple[Dict[str, QPointF], List[float]]:
        """Compute layout positions and branch centers."""
        if not self._model.nodes:
            return {}, []

        if nx:
            graph = nx.DiGraph()
            graph.add_nodes_from(self._model.nodes)
            graph.add_edges_from(self._model.edges)
            roots = [n for n in graph.nodes if graph.in_degree(n) == 0]
            depth_map = self._compute_depths_networkx(graph, roots)
        else:
            graph = None
            roots = self._find_roots(self._model.nodes, self._model.edges)
            depth_map = self._compute_depths(self._model.nodes, self._model.edges, roots)

        branch_index_map, branch_centers = self._assign_branches(graph, roots)
        positions: Dict[str, QPointF] = {}

        for node_id in self._model.nodes:
            depth = depth_map.get(node_id, 0)
            branch = branch_index_map.get(node_id, 0)
            x = branch_centers[branch]
            y = depth * self._config.vertical_spacing
            positions[node_id] = QPointF(x, y)

        return positions, branch_centers

    def _assign_branches(
        self, graph, roots: List[str]
    ) -> Tuple[Dict[str, int], List[float]]:
        branch_index_map: Dict[str, int] = {}
        branch_centers: List[float] = []
        branch_counter = 0

        for root in roots:
            children = self._children_of(graph, root)
            if not children:
                branch_index_map[root] = branch_counter
                branch_centers.append(branch_counter * self._config.horizontal_spacing)
                branch_counter += 1
                continue
            branch_index_map[root] = branch_counter
            branch_centers.append(branch_counter * self._config.horizontal_spacing)
            branch_counter += 1
            for child in children:
                branch_index_map.update(
                    self._assign_branch_to_subtree(graph, child, branch_counter)
                )
                branch_centers.append(branch_counter * self._config.horizontal_spacing)
                branch_counter += 1

        if not branch_centers:
            branch_centers = [0.0]
        return branch_index_map, branch_centers

    def _assign_branch_to_subtree(self, graph, node_id: str, branch_index: int) -> Dict[str, int]:
        mapping = {node_id: branch_index}
        for child in self._children_of(graph, node_id):
            mapping.update(self._assign_branch_to_subtree(graph, child, branch_index))
        return mapping

    def _children_of(self, graph, node_id: str) -> List[str]:
        if graph is not None:
            return list(graph.successors(node_id))
        return [dst for src, dst in self._model.edges if src == node_id]

    def _find_roots(self, nodes: Iterable[str], edges: Iterable[Tuple[str, str]]) -> List[str]:
        incoming = {dst for _, dst in edges}
        return [node for node in nodes if node not in incoming]

    def _compute_depths(
        self,
        nodes: Iterable[str],
        edges: Iterable[Tuple[str, str]],
        roots: List[str],
    ) -> Dict[str, int]:
        depth_map = {node: 0 for node in nodes}
        adjacency: Dict[str, List[str]] = {node: [] for node in nodes}
        for src, dst in edges:
            adjacency[src].append(dst)
        stack: List[Tuple[str, int]] = [(root, 0) for root in roots]
        while stack:
            node, depth = stack.pop()
            depth_map[node] = max(depth_map.get(node, 0), depth)
            for child in adjacency.get(node, []):
                stack.append((child, depth + 1))
        return depth_map

    def _compute_depths_networkx(self, graph, roots: List[str]) -> Dict[str, int]:
        depth_map = {node: 0 for node in graph.nodes}
        stack: List[Tuple[str, int]] = [(root, 0) for root in roots]
        while stack:
            node, depth = stack.pop()
            depth_map[node] = max(depth_map.get(node, 0), depth)
            for child in graph.successors(node):
                stack.append((child, depth + 1))
        return depth_map


if __name__ == "__main__":
    app = QApplication([])

    nodes = ["Root", "A", "B", "C", "D", "E"]
    edges = [
        ("Root", "A"),
        ("Root", "B"),
        ("A", "C"),
        ("A", "D"),
        ("B", "E"),
    ]

    widget = GraphViewWidget(nodes, edges)
    widget.nodePressed.connect(lambda node_id: print(f"Node pressed: {node_id}"))
    widget.edgePressed.connect(
        lambda src, dst: print(f"Edge pressed: {src} -> {dst}")
    )
    widget.nodeApproachingBranch.connect(
        lambda node_id, branch: print(f"{node_id} approaching branch {branch}")
    )
    widget.nodeDroppedOnBranch.connect(
        lambda node_id, branch: print(f"{node_id} dropped on branch {branch}")
    )

    widget.set_node_color("Root", "#ffe8cc")
    widget.set_edge_style("Root", "B", dotted=True)

    widget.resize(900, 600)
    widget.show()

    app.exec()
