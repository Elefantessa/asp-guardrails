import clingo

ctl = clingo.Control()
ctl.load("ASPPolicy/v1_tui_package_holiday_terms.lp")
ctl.load("cases/example_facts.lp")
ctl.ground([("base", [])])

def on_model(model):
    print("Answer set:", *model.symbols(atoms=True))

ctl.solve(on_model=on_model)
