"""
tools.py - FalkorDB Graph Reasoning Tools.

Provides 6 high-level graph analysis functions powered by Cypher queries:
1. impact_analysis(function_name, depth)
   - Downstream blast radius over CALLS and IMPORTS (in reverse).
2. suggest_reviewers(file_or_function)
   - Identifies code owners & authors connected to the target file/function.
3. explain_origin(function_name)
   - Traces the origin of a function back to Commits, Issues ('fixes #...'), and Authors.
4. shortest_path(a, b)
   - Discovers how two code elements are connected across multi-hop edges.
5. critical_nodes(top_n)
   - Degree centrality / PageRank assessing the riskiest architectural bottlenecks.
6. find_clusters()
   - Community detection grouping cohesive module clusters and dependency boundaries.

All tools return a standardized dictionary format:
    {"answer": ..., "path": [...]}
"""

import logging
import os
import sys
from typing import Any

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from blastradius.graph.db import FalkorDBClient, db_client

logger = logging.getLogger(__name__)


def format_path_string(path_obj: Any) -> str:
    """
    Serializes a FalkorDB Path object or custom edge sequence into a readable string:
    e.g. [Function:api/routes.py:login] --(CALLS)--> [Function:auth/jwt.py:verify]
    """
    if not path_obj:
        return ""
    if isinstance(path_obj, str):
        return path_obj

    if hasattr(path_obj, "nodes") and hasattr(path_obj, "edges"):
        nodes = path_obj.nodes() if callable(path_obj.nodes) else path_obj.nodes
        edges = path_obj.edges() if callable(path_obj.edges) else path_obj.edges

        parts = []
        for i, node in enumerate(nodes):
            props = getattr(node, "properties", {})
            name = (
                props.get("full_name")
                or props.get("path")
                or props.get("name")
                or props.get("id")
                or props.get("hash")
                or str(getattr(node, "id", "Node"))
            )
            labels = getattr(node, "labels", None)
            label = labels[0] if labels else "Node"
            parts.append(f"[{label}:{name}]")

            if i < len(edges):
                edge = edges[i]
                rel_type = (
                    getattr(edge, "relation", None)
                    or getattr(edge, "type", None)
                    or "RELATED_TO"
                )
                parts.append(f"--({rel_type})-->")

        return " ".join(parts)

    return str(path_obj)


def impact_analysis(
    function_name: str, depth: int = 3, client: FalkorDBClient | None = None
) -> dict[str, Any]:
    """
    Evaluates downstream blast radius: what could break if `function_name` changes.
    Performs reverse multi-hop traversal over CALLS and IMPORTS.

    Returns:
        {"answer": {...}, "path": [...]}
    """
    target_client = client or db_client
    paths: list[str] = []
    affected_functions: set[str] = set()
    affected_files: set[str] = set()

    # 1. Reverse traversal over CALLS (Callers calling target function)
    callers_query = f"""
    MATCH p = (caller:Function)-[:CALLS*1..{depth}]->(target:Function)
    WHERE target.name = $name OR target.full_name = $name
    RETURN caller.full_name AS caller, caller.file_path AS file, length(p) AS depth, p
    ORDER BY depth ASC
    """
    res_callers = target_client.query(callers_query, {"name": function_name})
    if res_callers and getattr(res_callers, "result_set", None):
        for row in res_callers.result_set:
            caller_name, file_path, d, path_obj = row[0], row[1], row[2], row[3]
            affected_functions.add(caller_name)
            if file_path:
                affected_files.add(file_path)
            formatted = format_path_string(path_obj)
            if formatted and formatted not in paths:
                paths.append(formatted)

    # 2. Reverse traversal over IMPORTS (Files importing the module containing target function)
    importers_query = f"""
    MATCH (f:File)-[:CONTAINS*1..2]->(target:Function)
    WHERE target.name = $name OR target.full_name = $name
    MATCH p = (importer:File)-[:IMPORTS*1..{depth}]->(f)
    RETURN importer.path AS importer, length(p) AS depth, p
    ORDER BY depth ASC
    """
    res_importers = target_client.query(importers_query, {"name": function_name})
    if res_importers and getattr(res_importers, "result_set", None):
        for row in res_importers.result_set:
            importer_path, d, path_obj = row[0], row[1], row[2]
            affected_files.add(importer_path)
            formatted = format_path_string(path_obj)
            if formatted and formatted not in paths:
                paths.append(formatted)

    answer = {
        "target": function_name,
        "max_depth": depth,
        "affected_functions": sorted(list(affected_functions)),
        "affected_files": sorted(list(affected_files)),
        "total_affected_functions": len(affected_functions),
        "total_affected_files": len(affected_files),
        "summary": (
            f"Modifying '{function_name}' has downstream impact on {len(affected_functions)} "
            f"functions across {len(affected_files)} files within depth {depth}."
        ),
    }

    return {"answer": answer, "path": paths}


def suggest_reviewers(
    file_or_function: str, client: FalkorDBClient | None = None
) -> dict[str, Any]:
    """
    Recommends reviewers by finding authors and code owners connected to the affected code.

    Returns:
        {"answer": {...}, "path": [...]}
    """
    target_client = client or db_client
    paths: list[str] = []
    reviewers_map: dict[str, dict[str, Any]] = {}

    # Query 1: Direct code ownership via OWNS edges
    owns_query = """
    MATCH (target_node)
    WHERE (target_node:File AND (target_node.path = $target OR target_node.name = $target))
       OR (target_node:Function AND (target_node.name = $target OR target_node.full_name = $target))
    MATCH (f:File)-[:CONTAINS*0..2]->(target_node)
    WITH f
    MATCH p = (a:Author)-[o:OWNS]->(f)
    RETURN a.name AS name, a.email AS email, o.score AS score, o.commits AS commits, o.lines_changed AS lines, p
    ORDER BY o.score DESC
    """
    res_owns = target_client.query(owns_query, {"target": file_or_function})
    if res_owns and getattr(res_owns, "result_set", None):
        for row in res_owns.result_set:
            name, email, score, commits, lines, path_obj = row[0], row[1], row[2], row[3], row[4], row[5]
            reviewers_map[email] = {
                "name": name,
                "email": email,
                "score": float(score or 0.0),
                "commits": int(commits or 0),
                "lines_changed": int(lines or 0),
                "role": "Designated Code Owner",
            }
            formatted = format_path_string(path_obj)
            if formatted and formatted not in paths:
                paths.append(formatted)

    # Query 2: Historical commit activity via AUTHORED and MODIFIED/MODIFIED_BY
    history_query = """
    MATCH (target_node)
    WHERE (target_node:File AND (target_node.path = $target OR target_node.name = $target))
       OR (target_node:Function AND (target_node.name = $target OR target_node.full_name = $target))
    MATCH (f:File)-[:CONTAINS*0..2]->(target_node)
    WITH f
    MATCH p = (a:Author)-[:AUTHORED]->(cm:Commit)-[m:MODIFIED|MODIFIED_BY]->(f)
    RETURN a.name AS name, a.email AS email, count(DISTINCT cm) AS commits_cnt,
           sum(COALESCE(m.lines, m.insertions + m.deletions, 0)) AS lines_sum, p
    ORDER BY commits_cnt DESC
    """
    res_hist = target_client.query(history_query, {"target": file_or_function})
    if res_hist and getattr(res_hist, "result_set", None):
        for row in res_hist.result_set:
            name, email, commits_cnt, lines_sum, path_obj = row[0], row[1], row[2], row[3], row[4]
            calc_score = round(commits_cnt * 10.0 + (lines_sum or 0) * 0.1, 1)
            if email not in reviewers_map:
                reviewers_map[email] = {
                    "name": name,
                    "email": email,
                    "score": calc_score,
                    "commits": int(commits_cnt),
                    "lines_changed": int(lines_sum or 0),
                    "role": "Frequent Contributor",
                }
            else:
                # Merge commit statistics
                reviewers_map[email]["commits"] = max(reviewers_map[email]["commits"], int(commits_cnt))
                reviewers_map[email]["lines_changed"] = max(reviewers_map[email]["lines_changed"], int(lines_sum or 0))

            formatted = format_path_string(path_obj)
            if formatted and formatted not in paths:
                paths.append(formatted)

    reviewers_list = sorted(
        list(reviewers_map.values()), key=lambda r: (r["score"], r["commits"]), reverse=True
    )

    answer = {
        "target": file_or_function,
        "reviewers": reviewers_list,
        "total_reviewers": len(reviewers_list),
        "summary": f"Found {len(reviewers_list)} subject matter expert reviewers for '{file_or_function}'.",
    }

    return {"answer": answer, "path": paths}


def explain_origin(
    function_name: str, client: FalkorDBClient | None = None
) -> dict[str, Any]:
    """
    Traces a function back through the graph to its introducing Commits,
    referenced Issues (e.g. 'fixes #123'), and original Authors.

    Returns:
        {"answer": {...}, "path": [...]}
    """
    target_client = client or db_client
    paths: list[str] = []
    authors_map: dict[str, dict[str, str]] = {}
    commits_map: dict[str, dict[str, Any]] = {}
    issues_map: dict[str, dict[str, Any]] = {}
    target_file = ""

    cypher = """
    MATCH (fn:Function)
    WHERE fn.name = $func_name OR fn.full_name = $func_name
    MATCH (f:File)-[:CONTAINS*1..2]->(fn)
    WITH f, fn
    MATCH p_cm = (cm:Commit)-[m:MODIFIED|MODIFIED_BY]->(f)
    MATCH p_auth = (a:Author)-[:AUTHORED]->(cm)
    OPTIONAL MATCH p_issue = (cm)-[:FIXES]->(i:Issue)
    RETURN fn.full_name AS func_name,
           f.path AS file_path,
           a.name AS author_name,
           a.email AS author_email,
           cm.hash AS commit_hash,
           cm.short_hash AS commit_short,
           cm.message AS commit_msg,
           i.id AS issue_id,
           i.title AS issue_title,
           p_cm, p_auth, p_issue
    """
    res = target_client.query(cypher, {"func_name": function_name})
    if res and getattr(res, "result_set", None):
        for row in res.result_set:
            (
                func_full,
                file_path,
                auth_name,
                auth_email,
                c_hash,
                c_short,
                c_msg,
                issue_id,
                issue_title,
                p_cm,
                p_auth,
                p_issue,
            ) = row

            target_file = file_path or target_file

            if auth_email:
                authors_map[auth_email] = {"name": auth_name, "email": auth_email}

            if c_hash:
                commits_map[c_hash] = {
                    "hash": c_hash,
                    "short_hash": c_short or c_hash[:7],
                    "message": c_msg,
                    "author": auth_name,
                }

            if issue_id:
                issues_map[issue_id] = {
                    "id": issue_id,
                    "title": issue_title or f"Issue {issue_id}",
                }

            for p_obj in (p_auth, p_cm, p_issue):
                if p_obj:
                    formatted = format_path_string(p_obj)
                    if formatted and formatted not in paths:
                        paths.append(formatted)

    authors_list = list(authors_map.values())
    commits_list = list(commits_map.values())
    issues_list = list(issues_map.values())

    answer = {
        "function": function_name,
        "file": target_file,
        "authors": authors_list,
        "commits": commits_list,
        "issues": issues_list,
        "summary": (
            f"Function '{function_name}' traces back to {len(commits_list)} commit(s) "
            f"authored by {len(authors_list)} contributor(s), addressing {len(issues_list)} issue(s)."
        ),
    }

    return {"answer": answer, "path": paths}


def shortest_path(
    a: str, b: str, client: FalkorDBClient | None = None
) -> dict[str, Any]:
    """
    Finds the shortest connecting call, import, or containment path between two code elements.

    Returns:
        {"answer": {...}, "path": [...]}
    """
    target_client = client or db_client
    paths: list[str] = []

    # 1. Directed search first (CALLS, IMPORTS, CONTAINS)
    directed_cypher = """
    MATCH p = (src)-[:CALLS|IMPORTS|CONTAINS*1..8]->(dst)
    WHERE (src.name = $a OR src.full_name = $a OR src.path = $a)
      AND (dst.name = $b OR dst.full_name = $b OR dst.path = $b)
    RETURN p, length(p) AS hops
    ORDER BY hops ASC
    LIMIT 1
    """
    res = target_client.query(directed_cypher, {"a": a, "b": b})
    found = False
    hops = -1

    if res and getattr(res, "result_set", None) and len(res.result_set) > 0:
        path_obj, hops = res.result_set[0][0], res.result_set[0][1]
        formatted = format_path_string(path_obj)
        if formatted:
            paths.append(formatted)
        found = True
    else:
        # 2. Undirected search fallback
        undirected_cypher = """
        MATCH p = (src)-[*1..8]-(dst)
        WHERE (src.name = $a OR src.full_name = $a OR src.path = $a)
          AND (dst.name = $b OR dst.full_name = $b OR dst.path = $b)
        RETURN p, length(p) AS hops
        ORDER BY hops ASC
        LIMIT 1
        """
        res_undir = target_client.query(undirected_cypher, {"a": a, "b": b})
        if res_undir and getattr(res_undir, "result_set", None) and len(res_undir.result_set) > 0:
            path_obj, hops = res_undir.result_set[0][0], res_undir.result_set[0][1]
            formatted = format_path_string(path_obj)
            if formatted:
                paths.append(formatted)
            found = True

    answer = {
        "source": a,
        "target": b,
        "hops": hops if found else -1,
        "connected": found,
        "summary": (
            f"Found connection between '{a}' and '{b}' in {hops} hop(s)."
            if found
            else f"No connecting path found between '{a}' and '{b}'."
        ),
    }

    return {"answer": answer, "path": paths}


def critical_nodes(
    top_n: int = 5, client: FalkorDBClient | None = None
) -> dict[str, Any]:
    """
    Calculates PageRank/degree centrality for code symbols to identify the riskiest architectural hubs.

    Returns:
        {"answer": {...}, "path": [...]}
    """
    target_client = client or db_client
    paths: list[str] = []
    nodes: list[dict[str, Any]] = []

    cypher = """
    MATCH (fn:Function)
    OPTIONAL MATCH p_in = (caller:Function)-[:CALLS]->(fn)
    OPTIONAL MATCH p_out = (fn)-[:CALLS]->(callee:Function)
    WITH fn, count(DISTINCT caller) AS in_degree, count(DISTINCT callee) AS out_degree,
         collect(DISTINCT p_in)[0..2] AS in_paths,
         collect(DISTINCT p_out)[0..2] AS out_paths
    WHERE in_degree > 0 OR out_degree > 0
    WITH fn, in_degree, out_degree, (in_degree * 3.0 + out_degree * 1.0) AS centrality_score,
         in_paths + out_paths AS related_paths
    ORDER BY centrality_score DESC, in_degree DESC
    LIMIT $top_n
    RETURN fn.full_name AS symbol,
           fn.name AS name,
           fn.file_path AS file,
           in_degree,
           out_degree,
           centrality_score,
           related_paths
    """
    res = target_client.query(cypher, {"top_n": top_n})
    if res and getattr(res, "result_set", None):
        for row in res.result_set:
            symbol, name, file_path, in_deg, out_deg, score, p_list = row
            tier = "CRITICAL" if score >= 10.0 else ("HIGH" if score >= 5.0 else "MEDIUM")
            nodes.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "file": file_path,
                    "in_degree": int(in_deg),
                    "out_degree": int(out_deg),
                    "centrality_score": float(score),
                    "risk_tier": tier,
                }
            )
            for p_obj in p_list:
                formatted = format_path_string(p_obj)
                if formatted and formatted not in paths:
                    paths.append(formatted)

    answer = {
        "top_n": top_n,
        "critical_nodes": nodes,
        "total_evaluated": len(nodes),
        "summary": f"Identified top {len(nodes)} critical code hubs based on incoming caller coupling.",
    }

    return {"answer": answer, "path": paths}


def find_clusters(
    client: FalkorDBClient | None = None
) -> dict[str, Any]:
    """
    Performs community detection across modules and files based on IMPORTS and CALLS coupling.

    Returns:
        {"answer": {...}, "path": [...]}
    """
    target_client = client or db_client
    paths: list[str] = []
    clusters_map: dict[str, dict[str, Any]] = {}

    # Query file-level import relationships and module structures
    cypher = """
    MATCH (f:File)
    OPTIONAL MATCH p_imp = (f)-[:IMPORTS]->(dep:File)
    OPTIONAL MATCH (f)-[:CONTAINS*1..2]->(fn:Function)
    OPTIONAL MATCH p_call = (fn)-[:CALLS]->(target_fn:Function)
    WHERE target_fn.file_path <> f.path
    WITH f,
         collect(DISTINCT dep.path) AS imported_files,
         collect(DISTINCT fn.name) AS functions,
         collect(DISTINCT p_imp) AS imp_paths,
         collect(DISTINCT p_call) AS call_paths
    RETURN f.path AS file_path,
           imported_files,
           functions,
           imp_paths + call_paths AS related_paths
    """
    res = target_client.query(cypher)
    if res and getattr(res, "result_set", None):
        for row in res.result_set:
            file_path, imports, functions, r_paths = row[0], row[1], row[2], row[3]
            # Infer module cluster from directory path
            norm_path = (file_path or "").replace("\\", "/")
            module_name = norm_path.split("/")[0] if "/" in norm_path else "root"
            cluster_id = f"module_{module_name}"

            if cluster_id not in clusters_map:
                clusters_map[cluster_id] = {
                    "cluster_id": cluster_id,
                    "module": module_name,
                    "files": set(),
                    "functions": set(),
                    "dependencies": set(),
                }

            clusters_map[cluster_id]["files"].add(norm_path)
            for fn in functions:
                if fn:
                    clusters_map[cluster_id]["functions"].add(fn)
            for imp in imports:
                if imp:
                    clusters_map[cluster_id]["dependencies"].add(imp)

            for p_obj in r_paths:
                formatted = format_path_string(p_obj)
                if formatted and formatted not in paths:
                    paths.append(formatted)

    formatted_clusters = []
    for c_id, c_data in sorted(clusters_map.items()):
        formatted_clusters.append(
            {
                "cluster_id": c_id,
                "module": c_data["module"],
                "files": sorted(list(c_data["files"])),
                "functions": sorted(list(c_data["functions"])),
                "dependencies": sorted(list(c_data["dependencies"])),
                "size": len(c_data["files"]) + len(c_data["functions"]),
            }
        )

    answer = {
        "clusters": formatted_clusters,
        "total_clusters": len(formatted_clusters),
        "summary": f"Detected {len(formatted_clusters)} cohesive module community clusters.",
    }

    return {"answer": answer, "path": paths}
