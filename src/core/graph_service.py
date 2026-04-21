"""
ASD v11.3 — Graph Service.

Local knowledge graph using NetworkX.
Uses pathlib for cross-platform path handling.
"""

import os
import logging
import pickle
from typing import Dict, Any, List

import networkx as nx
from src.config import settings

logger = logging.getLogger(__name__)


class GraphService:
    """Сервис для работы с локальным графом знаний (NetworkX)."""

    def __init__(self):
        self.graph_dir = settings.graphs_path
        self.graph_path = self.graph_dir / "knowledge_graph.gpickle"
        self.graph = self._load_or_create_graph()

    def _load_or_create_graph(self) -> nx.DiGraph:
        """Загружает граф с диска или создает новый."""
        if self.graph_path.exists():
            try:
                with open(self.graph_path, "rb") as f:
                    return pickle.load(f)
            except Exception as e:
                logger.error(f"Error loading graph: {e}. Creating a new one.")
                return nx.DiGraph()
        else:
            return nx.DiGraph()

    def save_graph(self):
        """Сохраняет текущее состояние графа на диск."""
        self.graph_dir.mkdir(parents=True, exist_ok=True)
        with open(self.graph_path, "wb") as f:
            pickle.dump(self.graph, f)

    def add_document(self, doc_id: str, metadata: Dict[str, Any]):
        """Добавляет узел-документ."""
        self.graph.add_node(doc_id, type="Document", **metadata)
        self.save_graph()

    def add_normative_act(self, act_id: str, title: str):
        """Добавляет узел нормативного акта."""
        self.graph.add_node(act_id, type="Normative_Act", title=title)
        self.save_graph()

    def add_reference(self, source_id: str, target_id: str, context: str = ""):
        """Добавляет связь (отсылку)."""
        if self.graph.has_node(source_id) and self.graph.has_node(target_id):
            self.graph.add_edge(source_id, target_id, relation="REFERENCES", context=context)
            self.save_graph()
        else:
            logger.warning(f"Failed to add edge {source_id} -> {target_id}. Nodes must exist.")

    def get_related_nodes(self, node_id: str, depth: int = 1) -> List[Dict[str, Any]]:
        """Ищет связанные узлы на заданной глубине."""
        if not self.graph.has_node(node_id):
            return []

        related = []
        # Простой BFS для поиска соседей
        edges = nx.bfs_edges(self.graph, source=node_id, depth_limit=depth)
        for u, v in edges:
            node_data = self.graph.nodes[v]
            related.append({"id": v, "data": node_data})

        return related


graph_service = GraphService()
