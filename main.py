from drafter import *
from dataclasses import dataclass
from bakery import assert_equal
import re

set_website_title("ChemYield")
set_site_information(
    author="Caitlyn Reese",
    description="Automated Chemistry Tutor",
    sources="AI Conversation.pdf",
    planning=["Final Project 0_ Pick a Problem.pdf", "Final Project 1_ Design Phase.pdf"],
    links=["https://github.com/caitlyn-reese/chemistry-tutor"]
)
hide_debug_information()
set_website_framed(False)

"""
Chemistry Yield Calculator
-------------------------
Drafter website for stoichiometry and reaction-heat calculations.

Advanced technique note:
- The formula parser uses regular expressions (re) to read element symbols
  and subscripts. It intentionally supports simple formulas such as H2O,
  CaCl2, and C6H12O6, but not parentheses or hydrates.
- The equation parser separates reactants/products and reads optional
  integer coefficients.
- This starter version uses a small atomic-mass dictionary so it can run
  in a basic Drafter/BlockPy environment without extra packages.
  For a production extension, replace formula_mass() with ChemPy's
  formula_to_composition()/atomic-weight facilities and add PubChem
  verification through its PUG REST API. Do not import ChemPy unless it
  is installed in the deployment environment.
- Heat of reaction is entered as kJ per balanced reaction as written.
"""

# Global constant is allowed by the project guidelines.
ATOMIC_MASSES = {
    "H": 1.008, "He": 4.0026, "Li": 6.94, "Be": 9.0122,
    "B": 10.81, "C": 12.011, "N": 14.007, "O": 15.999,
    "F": 18.998, "Ne": 20.180, "Na": 22.990, "Mg": 24.305,
    "Al": 26.982, "Si": 28.085, "P": 30.974, "S": 32.06,
    "Cl": 35.45, "Ar": 39.948, "K": 39.098, "Ca": 40.078,
    "Mn": 54.938, "Fe": 55.845, "Cu": 63.546, "Zn": 65.38,
    "Br": 79.904, "Ag": 107.868, "I": 126.904, "Ba": 137.327,
    "Pb": 207.2
}


@dataclass
class Reactant:
    """Store the starting and leftover information for one reactant."""
    formula: str
    coefficient: int
    starting_mass: float
    molar_mass: float
    starting_moles: float
    remaining_mass: float
    is_limiting: bool


@dataclass
class YieldResult:
    """Store the yield and heat results for the selected product."""
    product_formula: str
    theoretical_mass: float
    actual_mass: float
    percent_yield: float
    limiting_reactant: str
    heat_type: str
    heat_per_mole: float


@dataclass
class HistoryRecord:
    """A saved calculation summary for the history page."""
    equation: str
    product: str
    theoretical_mass: float
    actual_mass: float
    percent_yield: float
    limiting_reactant: str
    heat_type: str
    heat_per_mole: float


@dataclass
class State:
    """Keep user inputs, calculation results, history, and UI status."""
    equation: str
    mass_entry: str
    target_product: str
    actual_mass: float
    delta_h: float
    show_steps: bool
    reactants: list[Reactant]
    results: list[YieldResult]
    history: list[HistoryRecord]
    message: str


def formula_atoms(formula: str) -> dict[str, int]:
    """Convert a simple chemical formula into element counts."""
    tokens = re.findall(r"([A-Z][a-z]?)([0-9]*)", formula)
    if not tokens:
        raise ValueError("Could not read formula: " + formula)

    rebuilt = ""
    atoms = {}
    for element, amount_text in tokens:
        rebuilt += element + amount_text
        if element not in ATOMIC_MASSES:
            raise ValueError("Atomic mass is unavailable for " + element)
        amount = int(amount_text) if amount_text else 1
        atoms[element] = atoms.get(element, 0) + amount

    if rebuilt != formula:
        raise ValueError("Use a simple formula without parentheses: " + formula)
    return atoms


def formula_mass(formula: str) -> float:
    """Calculate molar mass from the atomic-mass dictionary."""
    atoms = formula_atoms(formula)
    mass = 0.0
    for element in atoms:
        mass += ATOMIC_MASSES[element] * atoms[element]
    return mass


def parse_term(term: str) -> tuple[int, str]:
    """Read a reaction term like '2H2' or 'H2O'."""
    cleaned = term.strip().replace(" ", "")
    match = re.fullmatch(r"([0-9]*)([A-Z][A-Za-z0-9]*)", cleaned)
    if match is None:
        raise ValueError("Cannot parse reaction term: " + term)

    coefficient_text = match.group(1)
    formula = match.group(2)
    coefficient = int(coefficient_text) if coefficient_text else 1

    if coefficient <= 0:
        raise ValueError("Reaction coefficients must be positive.")
    formula_atoms(formula)
    return coefficient, formula


def parse_side(side: str) -> list[tuple[int, str]]:
    """Parse one side of a reaction into coefficient/formula pairs."""
    terms = side.split("+")
    parsed = []
    for term in terms:
        if term.strip() == "":
            raise ValueError("A reaction side has an empty term.")
        parsed.append(parse_term(term))
    return parsed


def parse_equation(equation: str) -> tuple[list, list]:
    """Split a reaction equation into reactants and products."""
    if "->" in equation:
        sides = equation.split("->")
    elif "=" in equation:
        sides = equation.split("=")
    else:
        raise ValueError("Use an arrow such as H2 + O2 -> H2O.")

    if len(sides) != 2:
        raise ValueError("Enter exactly one reaction arrow.")
    reactants = parse_side(sides[0])
    products = parse_side(sides[1])
    return reactants, products


def total_atoms(terms: list) -> dict[str, int]:
    """Count atoms on one side, including reaction coefficients."""
    totals = {}
    for coefficient, formula in terms:
        atoms = formula_atoms(formula)
        for element in atoms:
            totals[element] = totals.get(element, 0)
            totals[element] += atoms[element] * coefficient
    return totals


def is_balanced(reactants: list, products: list) -> bool:
    """Return whether both sides contain the same number of each atom."""
    return total_atoms(reactants) == total_atoms(products)


def parse_mass_entry(mass_entry: str) -> dict[str, float]:
    """Read masses written one per line as Formula: mass_in_grams."""
    masses = {}
    for line in mass_entry.split("\n"):
        if line.strip() == "":
            continue
        pieces = line.split(":")
        if len(pieces) != 2:
            raise ValueError("Use one line per reactant, like H2: 5.0")
        formula = pieces[0].strip()
        mass = float(pieces[1].strip())
        formula_atoms(formula)
        if mass <= 0:
            raise ValueError("Starting reactant masses must be above zero.")
        masses[formula] = mass
    return masses


def calculate_yield(equation: str, mass_entry: str, target_product: str,
                    actual_mass: float, delta_h: float) -> tuple[list, YieldResult]:
    """Calculate limiting reactant, yield, leftovers, and reaction heat."""
    reactants, products = parse_equation(equation)

    if not is_balanced(reactants, products):
        raise ValueError("This equation is not balanced. Fix coefficients first.")
    if actual_mass < 0:
        raise ValueError("Actual product mass cannot be negative.")

    product_coefficient = 0
    for coefficient, formula in products:
        if formula == target_product:
            product_coefficient = coefficient

    if product_coefficient == 0:
        raise ValueError("Target product must appear on the product side.")

    masses = parse_mass_entry(mass_entry)
    for coefficient, formula in reactants:
        if formula not in masses:
            raise ValueError("Missing starting mass for " + formula)

    # The reaction extent is the smallest available moles/coefficient.
    reaction_extents = []
    for coefficient, formula in reactants:
        moles = masses[formula] / formula_mass(formula)
        reaction_extents.append(moles / coefficient)

    extent = min(reaction_extents)
    limiting_index = reaction_extents.index(extent)
    limiting_formula = reactants[limiting_index][1]
    theoretical_product_moles = extent * product_coefficient
    theoretical_mass = theoretical_product_moles * formula_mass(target_product)

    if theoretical_mass <= 0:
        raise ValueError("The theoretical yield must be positive.")
    percent_yield = actual_mass / theoretical_mass * 100

    reactant_results = []
    for coefficient, formula in reactants:
        molar_mass = formula_mass(formula)
        starting_moles = masses[formula] / molar_mass
        consumed_moles = coefficient * extent
        remaining_moles = starting_moles - consumed_moles
        if remaining_moles < 0 and remaining_moles > -0.0000001:
            remaining_moles = 0
        remaining_mass = remaining_moles * molar_mass

        reactant_results.append(
            Reactant(
                formula, coefficient, masses[formula], molar_mass,
                starting_moles, remaining_mass,
                formula == limiting_formula
            )
        )

    if delta_h < 0:
        heat_type = "Exothermic (releases heat)"
    elif delta_h > 0:
        heat_type = "Endothermic (absorbs heat)"
    else:
        heat_type = "Thermoneutral (no heat change entered)"

    heat_per_mole = delta_h / product_coefficient
    result = YieldResult(
        target_product, theoretical_mass, actual_mass, percent_yield,
        limiting_formula, heat_type, heat_per_mole
    )
    return reactant_results, result


def site_header(title: str) -> list:
    """Create shared navigation for every page."""
    return [
        Header("ChemYield | " + title),
        Link("Home", "index"), "  |  ",
        Link("Calculator", "calculator"), "  |  ",
        Link("History", "history"), "  |  ",
        Link("Chemistry Guide", "guide"), "  |  ",
        Link("About", "about"), "\n",
        HorizontalRule()
    ]


@route
def index(state: State) -> Page:
    """Show the homepage and the most recent calculation."""
    content = site_header("Home") + [
        Header("Reaction calculations, made clearer", 2),
        "ChemYield calculates limiting reactants, theoretical yield, "
        "percent yield, leftover reactants, and reaction heat.",
        "\n\n",
        Button("Start a calculation", "calculator"),
        Button("View saved calculations", "history"),
        Button("Read the chemistry guide", "guide"),
        "\n\n",
        Header("Latest result", 3)
    ]

    if state.results:
        latest = state.results[-1]
        content += [
            "Product: " + latest.product_formula + "\n",
            "Theoretical yield: " + str(round(latest.theoretical_mass, 4))
            + " g\n",
            "Percent yield: " + str(round(latest.percent_yield, 2)) + "%\n",
            "Limiting reactant: " + latest.limiting_reactant + "\n"
        ]
    else:
        content.append("No calculations yet. Try the calculator!")
    content += ["\n", state.message]
    return Page(state, content)


@route
def calculator(state: State) -> Page:
    """Show the reaction calculator form."""
    return Page(state, site_header("Calculator") + [
        Header("Enter your reaction", 2),
        "Use a balanced equation. Example: 2H2 + O2 -> 2H2O",
        "\n",
        "Balanced equation:",
        TextArea("equation", state.equation, rows=2),
        "\n",
        "Starting masses (one reactant per line, grams):",
        TextArea("mass_entry", state.mass_entry, rows=4),
        "\n",
        "Product formula to calculate:",
        TextBox("target_product", state.target_product),
        "\n",
        "Actual harvested product mass (g):",
        TextBox("actual_mass", state.actual_mass, "number"),
        "\n",
        "Heat of reaction ΔH (kJ per equation as written):",
        TextBox("delta_h", state.delta_h, "number"),
        "\n",
        CheckBox("show_steps", state.show_steps),
        " Show calculation details\n",
        Button("Calculate reaction", "calculate"),
        "\n",
        state.message
    ])


@route
def calculate(state: State, equation: str, mass_entry: str,
              target_product: str, actual_mass: float,
              delta_h: float, show_steps: bool) -> Page:
    """Validate submitted inputs and save a calculation."""
    state.equation = equation
    state.mass_entry = mass_entry
    state.target_product = target_product.strip()
    state.actual_mass = actual_mass
    state.delta_h = delta_h
    state.show_steps = show_steps

    try:
        reactants, result = calculate_yield(
            equation, mass_entry, state.target_product, actual_mass, delta_h
        )
        state.reactants = reactants
        state.results = [result]
        state.history.append(
            HistoryRecord(
                equation, result.product_formula, result.theoretical_mass,
                result.actual_mass, result.percent_yield,
                result.limiting_reactant, result.heat_type,
                result.heat_per_mole
            )
        )
        state.message = "Calculation completed successfully."
        return results(state)
    except ValueError as error:
        state.results = []
        state.message = "Input problem: " + str(error)
        return calculator(state)


@route
def results(state: State) -> Page:
    """Display the most recent calculation and leftover masses."""
    content = site_header("Results") + [Header("Calculation results", 2)]

    if not state.results:
        content += [
            "There is no valid result yet.\n",
            state.message,
            Button("Return to calculator", "calculator")
        ]
        return Page(state, content)

    result = state.results[-1]
    content += [
        "Reaction: " + state.equation + "\n",
        "Selected product: " + result.product_formula + "\n",
        "Limiting reactant: " + result.limiting_reactant + "\n",
        "Theoretical yield: " + str(round(result.theoretical_mass, 4))
        + " g\n",
        "Actual yield: " + str(round(result.actual_mass, 4)) + " g\n",
        "Percent yield: " + str(round(result.percent_yield, 2)) + "%\n",
        "Heat classification: " + result.heat_type + "\n",
        "Heat per mole of product: "
        + str(round(result.heat_per_mole, 4)) + " kJ/mol\n",
        "\n",
        Header("Reactant leftovers", 3)
    ]

    # Meaningful loop over the list of Reactant dataclass instances.
    for reactant in state.reactants:
        status = "LIMITING" if reactant.is_limiting else "Excess"
        content.append(
            reactant.formula + " — " + status + " — remaining: "
            + str(round(reactant.remaining_mass, 4)) + " g\n"
        )

    if state.show_steps:
        content += [
            "\n",
            Header("How the calculation works", 3),
            "1. Convert each starting mass to moles using mass / molar mass.\n",
            "2. Divide each reactant's moles by its equation coefficient.\n",
            "3. The smallest value identifies the limiting reactant.\n",
            "4. Use the limiting reactant to find product moles and grams.\n",
            "5. Percent yield = actual yield / theoretical yield × 100.\n",
            "6. Remaining mass = starting mass − mass consumed.\n"
        ]

    content += [
        "\n",
        Button("New calculation", "calculator"),
        Button("View history", "history")
    ]
    return Page(state, content)


@route
def history(state: State) -> Page:
    """Show saved calculation summaries."""
    content = site_header("History") + [
        Header("Saved calculations", 2)
    ]

    if not state.history:
        content.append("Your history is empty.")
    else:
        # Loop over saved HistoryRecord instances.
        for record in state.history:
            content += [
                "Equation: " + record.equation + "\n",
                "Product: " + record.product + "\n",
                "Theoretical yield: "
                + str(round(record.theoretical_mass, 4)) + " g\n",
                "Actual yield: " + str(round(record.actual_mass, 4)) + " g\n",
                "Percent yield: " + str(round(record.percent_yield, 2))
                + "%\n",
                "Limiting reactant: " + record.limiting_reactant + "\n",
                "Heat: " + record.heat_type + "\n",
                "Heat per mole: " + str(round(record.heat_per_mole, 4))
                + " kJ/mol\n",
                HorizontalRule()
            ]

    content += [
        Button("Clear history", "clear_history"),
        Button("Back to calculator", "calculator")
    ]
    return Page(state, content)


@route
def clear_history(state: State) -> Page:
    """Clear saved records after the user selects the button."""
    state.history = []
    state.message = "Calculation history cleared."
    return history(state)


@route
def guide(state: State) -> Page:
    """Explain the chemistry ideas used by the calculator."""
    return Page(state, site_header("Chemistry Guide") + [
        Header("Chemistry concepts", 2),
        Header("Limiting reactant", 3),
        "The limiting reactant is consumed first and determines the "
        "maximum amount of product.",
        "\n",
        Header("Theoretical yield", 3),
        "The theoretical yield is the maximum product mass predicted "
        "from the limiting reactant and the balanced equation.",
        "\n",
        Header("Percent yield", 3),
        "Percent yield = actual yield / theoretical yield × 100%.",
        "\n",
        Header("Reaction heat", 3),
        "A negative ΔH is exothermic (heat released). A positive ΔH is "
        "endothermic (heat absorbed).",
        "\n",
        "This site treats ΔH as kJ per balanced reaction exactly as entered. "
        "Heat per mole of selected product = ΔH / product coefficient.",
        "\n",
        Header("Formula support", 3),
        "The starter parser supports simple formulas with element symbols "
        "and numeric subscripts. Parentheses and hydrates are not supported.",
        "\n",
        Button("Try a calculation", "calculator")
    ])


@route
def about(state: State) -> Page:
    """Describe the purpose, assumptions, and limitations of the site."""
    return Page(state, site_header("About") + [
        Header("About ChemYield", 2),
        "ChemYield is a student chemistry assistant for practicing "
        "stoichiometry and reaction-heat calculations.",
        "\n",
        "It is based on introductory chemical reaction and stoichiometry "
        "principles, including limiting reactants and percent yield.",
        "\n",
        "Important: this version uses a built-in atomic mass table. It does "
        "not make live PubChem requests or use ChemPy automatically. "
        "Those can be added when the deployment environment supports "
        "the packages and internet access.",
        "\n",
        "The results are intended for learning and should be checked "
        "against class materials.",
        "\n",
        Button("Open calculator", "calculator")
    ])


# ------------------------- Unit tests -------------------------

def test_formula_mass() -> None:
    """Test common molar masses."""
    assert_equal(round(formula_mass("H2O"), 3), 18.015)
    assert_equal(round(formula_mass("CO2"), 3), 44.009)


def test_equation_balance() -> None:
    """Test equation parsing and balance checking."""
    reactants, products = parse_equation("2H2 + O2 -> 2H2O")
    assert_equal(is_balanced(reactants, products), True)
    assert_equal(is_balanced(*parse_equation("H2 + O2 -> H2O")), False)


def test_yield_calculation() -> None:
    """Test limiting reactant, theoretical yield, and percent yield."""
    reactants, result = calculate_yield(
        "2H2 + O2 -> 2H2O",
        "H2: 8.064\nO2: 32.0",
        "H2O",
        30.0,
        -483.6
    )
    assert_equal(result.limiting_reactant, "O2")
    assert_equal(round(result.theoretical_mass, 2), 36.03)
    assert_equal(round(result.percent_yield, 2), 83.26)
    assert_equal(round(reactants[0].remaining_mass, 2), 4.03)


def test_heat_classification() -> None:
    """Check exothermic and endothermic sign conventions."""
    _, exo = calculate_yield(
        "2H2 + O2 -> 2H2O", "H2: 8.064\nO2: 32",
        "H2O", 30, -483.6
    )
    _, endo = calculate_yield(
        "2H2 + O2 -> 2H2O", "H2: 8.064\nO2: 32",
        "H2O", 30, 483.6
    )
    assert_equal(exo.heat_type.startswith("Exothermic"), True)
    assert_equal(endo.heat_type.startswith("Endothermic"), True)


# Run helper-function unit tests before launching the website.
test_formula_mass()
test_equation_balance()
test_yield_calculation()
test_heat_classification()

# Site metadata required for project deployment.
set_site_information(
    "Your Name",
    "ChemYield: a chemistry stoichiometry and yield calculator.",
    "OpenStax Chemistry 2e, Chapter 4; ChemPy documentation; PubChem.",
    "Add the planning document filename here before submission.",
    ["https://github.com/your-username/your-project"]
)

# Initial state. Lists are instance fields, not global mutable variables.
start_server(
    State(
        equation="2H2 + O2 -> 2H2O",
        mass_entry="H2: 4.032\nO2: 32.0",
        target_product="H2O",
        actual_mass=30.0,
        delta_h=-483.6,
        show_steps=True,
        reactants=[],
        results=[],
        history=[],
        message="Welcome! Enter a balanced equation to begin."
    )
)
