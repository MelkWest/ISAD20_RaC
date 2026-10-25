import os
import re
import xml.etree.ElementTree as ET
import streamlit as st

st.set_page_config(
    page_title="Generic BPMN XML Decision Engine", page_icon="⚙️", layout="centered"
)

# XML Namespaces standard in Camunda 8 / BPMN 2.0
NAMESPACES = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "zeebe": "http://camunda.org/schema/zeebe/1.0",
}


class DynamicBPMNEngine:
  """Dynamic Execution Engine that parses and executes any standard BPMN 2.0 XML process model."""

  def __init__(self, xml_filepath):
    self.filepath = xml_filepath
    self.tree = ET.parse(xml_filepath)
    self.root = self.tree.getroot()
    self.nodes = {}
    self.flows = {}
    self._parse_model()

  def _parse_model(self):
    process = self.root.find("bpmn:process", NAMESPACES)
    if process is None:
      raise ValueError(
          "Invalid BPMN XML: No <bpmn:process> element found in model."
      )

    # 1. Parse Sequence Flows
    for flow in process.findall("bpmn:sequenceFlow", NAMESPACES):
      flow_id = flow.attrib.get("id")
      source = flow.attrib.get("sourceRef")
      target = flow.attrib.get("targetRef")
      name = flow.attrib.get("name", "")

      cond_elem = flow.find("bpmn:conditionExpression", NAMESPACES)
      expr = cond_elem.text.strip() if cond_elem is not None else None

      self.flows[flow_id] = {
          "source": source,
          "target": target,
          "name": name,
          "expression": expr,
      }

    # 2. Parse Gateways, Events, and Tasks
    for child in process:
      tag = child.tag.split("}")[-1]
      if tag in [
          "startEvent",
          "endEvent",
          "exclusiveGateway",
          "task",
          "userTask",
      ]:
        node_id = child.attrib.get("id")
        node_name = child.attrib.get("name", node_id)

        incoming = [
            elem.text
            for elem in child.findall("bpmn:incoming", NAMESPACES)
            if elem.text
        ]
        outgoing = [
            elem.text
            for elem in child.findall("bpmn:outgoing", NAMESPACES)
            if elem.text
        ]

        if not outgoing:
          outgoing = [
              f_id for f_id, f in self.flows.items() if f["source"] == node_id
          ]
        if not incoming:
          incoming = [
              f_id for f_id, f in self.flows.items() if f["target"] == node_id
          ]

        self.nodes[node_id] = {
            "type": tag,
            "name": node_name,
            "incoming": incoming,
            "outgoing": outgoing,
        }

  def get_start_node(self):
    for node_id, data in self.nodes.items():
      if data["type"] == "startEvent":
        return node_id
    raise ValueError("No startEvent found in BPMN XML model.")

  def evaluate_feel_condition(self, expression, variables):
    """Evaluates Camunda FEEL expressions dynamically against current user variables."""
    if not expression:
      return True

    clean_expr = expression.lstrip("=").strip()
    match = re.match(r"^([a-zA-Z0-9_]+)\s*(=|!=|>|<|>=|<=)\s*(.+)$", clean_expr)
    if not match:
      return False

    var_name, op, raw_val = (
        match.group(1).strip(),
        match.group(2).strip(),
        match.group(3).strip(),
    )

    if var_name not in variables:
      return False

    actual_val = variables[var_name]

    if raw_val.lower() == "true":
      target_val = True
    elif raw_val.lower() == "false":
      target_val = False
    elif (raw_val.startswith('"') and raw_val.endswith('"')) or (
        raw_val.startswith("'") and raw_val.endswith("'")
    ):
      target_val = raw_val[1:-1]
    else:
      try:
        target_val = float(raw_val) if "." in raw_val else int(raw_val)
      except ValueError:
        target_val = raw_val

    if op in ["=", "=="]:
      return actual_val == target_val
    elif op == "!=":
      return actual_val != target_val
    elif op == ">":
      return actual_val > target_val
    elif op == "<":
      return actual_val < target_val
    elif op == ">=":
      return actual_val >= target_val
    elif op == "<=":
      return actual_val <= target_val

    return False


# Helper function to convert camel/snake_case variables into clean human questions
import re


def humanize_variable(var_name):
  if not var_name:
    return ""
  # 1. Replace underscores with spaces
  s = var_name.replace("_", " ")
  # 2. Insert space before capital letters for camelCase (e.g., didVictimDie -> did Victim Die)
  s = re.sub(r"(?<!^)(?=[A-Z])", " ", s)
  # 3. Clean up extra spaces, make lowercase, and capitalize the first letter
  s = " ".join(s.split()).lower()
  return s.capitalize()


# Helper function to format choice values nicely
def humanize_value(val):
  if isinstance(val, bool):
    return "Yes" if val else "No"
  if isinstance(val, str):
    return val.replace("_", " ").title()
  return str(val)


# Streamlit UI
st.title("⚙️ Generic BPMN XML Decision Engine")
st.caption(
    "Parses and executes standard BPMN 2.0 XML process diagrams dynamically"
)

# Sidebar File Selection / Upload
st.sidebar.title("📁 BPMN Model Source")
bpmn_file = st.sidebar.file_uploader(
    "Upload BPMN File (.bpmn)", type=["bpmn", "xml"]
)

default_filename = "RaC_Decision_Tree.bpmn"
if not bpmn_file and os.path.exists(default_filename):
  xml_path = default_filename
  st.sidebar.info(f"Loaded default local model: `{default_filename}`")
elif bpmn_file:
  xml_path = "temp_uploaded_model.bpmn"
  with open(xml_path, "wb") as f:
    f.write(bpmn_file.getbuffer())
  st.sidebar.success(f"Loaded uploaded model: `{bpmn_file.name}`")
else:
  st.warning(
      "Please upload a `.bpmn` model file or place `RaC_Decision_Tree.bpmn` in"
      " the working directory."
  )
  st.stop()

# Initialize Engine
engine = DynamicBPMNEngine(xml_path)


# Helper function to auto-skip joining / single-outgoing gateways
def advance_through_joins(node_id):
  while True:
    if node_id not in engine.nodes:
      break
    node = engine.nodes[node_id]
    if node["type"] == "exclusiveGateway" and len(node["outgoing"]) <= 1:
      if node["outgoing"]:
        next_flow = engine.flows[node["outgoing"][0]]
        node_id = next_flow["target"]
        if node_id not in st.session_state.history:
          st.session_state.history.append(node_id)
      else:
        break
    else:
      break
  return node_id


# Initialize Session State
if "current_node" not in st.session_state:
  start_id = engine.get_start_node()
  first_flow_id = engine.nodes[start_id]["outgoing"][0]
  target_id = engine.flows[first_flow_id]["target"]
  st.session_state.history = [start_id, target_id]
  st.session_state.variables = {}
  st.session_state.current_node = advance_through_joins(target_id)

st.sidebar.markdown("---")
if st.sidebar.button("🗑️ Restart Process Execution"):
  start_id = engine.get_start_node()
  first_flow_id = engine.nodes[start_id]["outgoing"][0]
  target_id = engine.flows[first_flow_id]["target"]
  st.session_state.history = [start_id, target_id]
  st.session_state.variables = {}
  st.session_state.current_node = advance_through_joins(target_id)
  st.rerun()

curr_node_id = st.session_state.current_node
curr_node = engine.nodes[curr_node_id]

# --- DISPLAY PROCESS STEP ---
if curr_node["type"] == "endEvent":
  st.success(f"### 🏁 Reached End Event: `{curr_node['name']}`")
  st.markdown(f"**Final Outcome Node ID:** `{curr_node_id}`")

  st.markdown("---")
  st.subheader("🔍 Dynamically Executed Path")
  path_names = [
      engine.nodes[n]["name"] if n in engine.nodes else n
      for n in st.session_state.history
  ]
  st.code(" ➔ ".join(path_names))

  st.subheader("📋 Recorded Process Variables")
  # Display variables with human-readable keys and values for better UX
  readable_vars = {
      humanize_variable(k): humanize_value(v)
      for k, v in st.session_state.variables.items()
  }
  st.json(readable_vars)

elif curr_node["type"] == "exclusiveGateway":
  st.subheader(f"🔀 Gateway Evaluation")

  outgoing_flows = [engine.flows[f_id] for f_id in curr_node["outgoing"]]

  req_var = None
  expr_type = "boolean"
  string_options = []

  for flow in outgoing_flows:
    expr = flow["expression"]
    if expr:
      clean_expr = expr.lstrip("=").strip()
      match = re.match(
          r"^([a-zA-Z0-9_]+)\s*(=|!=|>|<|>=|<=)\s*(.+)$", clean_expr
      )
      if match:
        req_var = match.group(1).strip()
        raw_val = match.group(3).strip()
        if (raw_val.startswith('"') and raw_val.endswith('"')) or (
            raw_val.startswith("'") and raw_val.endswith("'")
        ):
          expr_type = "string"
          val_str = raw_val[1:-1]
          if val_str not in string_options:
            string_options.append(val_str)

  human_question = humanize_variable(req_var)
  st.markdown(f"#### {human_question}")
  st.caption(f"Process Gateway: `{curr_node['name']}`")

  if expr_type == "boolean":
    user_val = st.radio(
        "Select your answer:",
        options=[None, True, False],
        format_func=lambda x: (
            "Select an option..." if x is None else ("Yes" if x else "No")
        ),
        key=f"input_{curr_node_id}",
    )
  else:
    user_val = st.selectbox(
        "Select an option:",
        options=[None] + string_options,
        format_func=lambda x: (
            "Select act severity..." if x is None else humanize_value(x)
        ),
        key=f"input_{curr_node_id}",
    )

  if st.button(
      "Evaluate Gateway & Proceed ➔",
      type="primary",
      disabled=(user_val is None),
  ):
    st.session_state.variables[req_var] = user_val

    next_node_id = None
    default_node_id = None

    for flow in outgoing_flows:
      expr = flow["expression"]
      if not expr:
        default_node_id = flow["target"]
      elif engine.evaluate_feel_condition(expr, st.session_state.variables):
        next_node_id = flow["target"]
        break

    if not next_node_id:
      next_node_id = default_node_id

    if next_node_id:
      st.session_state.history.append(next_node_id)
      st.session_state.current_node = advance_through_joins(next_node_id)
      st.rerun()
    else:
      st.error(
          "No outgoing path condition was satisfied for the selected value!"
      )