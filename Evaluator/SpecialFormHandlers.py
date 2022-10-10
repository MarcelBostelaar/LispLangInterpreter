from Config.langConfig import SpecialForms
from Evaluator.Classes import StackFrame, Kind, sExpression, StackReturnValue, UserLambda, List
from Evaluator.SupportFunctions import dereference, MustBeKind, SpecialFormSlicer, QuoteCode


def handleSpecialFormCond(currentFrame: StackFrame):
    # eval condition, if true, return true unevaluated, else return falsepath unevaluated
    [[condAtom, condition, truePath, falsePath], tail] = \
        SpecialFormSlicer(currentFrame, SpecialForms.cond)
    if not currentFrame.isFullyEvaluated(1):
        return currentFrame.SubEvaluate(1)
    MustBeKind(currentFrame, condition, "Tried to evaluate an conditional, value to evaluate not a boolean",
               Kind.Boolean)
    if condition.value:
        path = truePath
    else:
        path = falsePath
    return currentFrame.withExecutionState(sExpression([path] + tail))


def handleSpecialFormLambda(currentFrame: StackFrame):
    [[_, args, body], rest] = SpecialFormSlicer(currentFrame, SpecialForms.Lambda)
    lambdaerr = "First arg after lambda must be a flat list/s expression of names"
    MustBeKind(currentFrame, args, lambdaerr, Kind.sExpression)
    [MustBeKind(currentFrame, x, lambdaerr, Kind.Reference) for x in args.value]
    MustBeKind(currentFrame, body, "Body of a lambda must be an s expression or a single name",
               Kind.sExpression, Kind.Reference)
    return currentFrame.withExecutionState(
        sExpression([UserLambda([z.value for z in args.value], body, currentFrame)] + rest)
    )


def handleSpecialFormLet(currentFrame: StackFrame):
    [[let, name, value], tail] = SpecialFormSlicer(currentFrame, SpecialForms.let)
    MustBeKind(currentFrame, name, "The first arg after a let must be a name", Kind.Reference)
    if not currentFrame.isFullyEvaluated(2):
        return currentFrame.SubEvaluate(2)
    return currentFrame.addScopedRegularValue(name.value, value).withExecutionState(tail)


def handleSpecialFormList(currentFrame):
    """
    Evaluate the items in snd into their fully evaluated form.
    :param currentFrame:
    :return:
    """
    [[listAtom, snd], tail] = SpecialFormSlicer(currentFrame, SpecialForms.list)
    MustBeKind(currentFrame, snd, "Item after list must be a list", Kind.sExpression)

    #Walk over the snd, save the first instance of a subexpression into new stack expression
    # and replace with a stack return value in the list, the following expressions as is
    newStackExpression = None
    listMapped = []
    for i in snd.value:
        if i.kind == Kind.sExpression:
            if newStackExpression is None:
                listMapped.append(StackReturnValue())
                newStackExpression = i
            else:
                listMapped.append(i)
        else:
            listMapped.append(dereference(currentFrame.withExecutionState(i)))

    # if a subexpression was found and replaced, make it into a new stackframe, with parent being the updates list
    if newStackExpression is not None:
        currentFrame = currentFrame.withExecutionState(sExpression([listAtom, sExpression(listMapped)] + tail))
        newStack = currentFrame.child(newStackExpression)
        return newStack
    #No subexpression found, all subitems are evaluated
    return currentFrame.withExecutionState(List(listMapped))


def verifyHandlerQuotekeyValuePairs(callingFrame: StackFrame, keyValue):
    errMessage = "Handlers must be key value pairs of a quoted name and a function"

    MustBeKind(callingFrame, keyValue, errMessage, Kind.List)
    for i in keyValue.value:
        MustBeKind(callingFrame, i, errMessage, Kind.List)
        if len(i.value) != 2:
            callingFrame.throwError(errMessage)
        MustBeKind(callingFrame, i.value[0], errMessage, Kind.QuotedName)
        MustBeKind(callingFrame, i.value[0], errMessage, Kind.Lambda)


def handleSpecialFormHandle(currentFrame: StackFrame) -> StackFrame:
    [[handlerWord, codeToEvaluate, handlerQuotekeyValuePairs, stateSeed], tail] = SpecialFormSlicer(currentFrame, SpecialForms.handle)

    if not currentFrame.isFullyEvaluated(2):#handlerQuotekeyValuePairs
        return currentFrame.SubEvaluate(2)
    if not currentFrame.isFullyEvaluated(3):#stateSeed
        return currentFrame.SubEvaluate(3)

    verifyHandlerQuotekeyValuePairs(currentFrame, handlerQuotekeyValuePairs)

    old = currentFrame.withExecutionState(sExpression([StackReturnValue()] + tail))
    branchPoint = old.child(HandlerBranchPoint())
    newFrame = old.child(codeToEvaluate)
    for i in handlerQuotekeyValuePairs.value:
        newFrame = newFrame.addHandler(i.value[0].value, i.value[1])
    newFrame.withHandlerState(stateSeed)
    return newFrame


def ExecuteSpecialForm(currentFrame: StackFrame) -> StackFrame:
    name = currentFrame.executionState.value[0].value
    if name == SpecialForms.Lambda.value.keyword:
        return handleSpecialFormLambda(currentFrame)

    if name == SpecialForms.macro.value.keyword:
        # ignore for this implementation, interpreter doesn't support eval yet
        [_, rest] = SpecialFormSlicer(currentFrame, SpecialForms.macro)
        return currentFrame.withExecutionState(rest)

    if name == SpecialForms.let.value.keyword:
        return handleSpecialFormLet(currentFrame)

    if name == SpecialForms.quote.value.keyword:
        # quotes item directly after it
        [[_, snd], tail] = SpecialFormSlicer(currentFrame, SpecialForms.quote)
        newSnd = QuoteCode(currentFrame, snd)
        return currentFrame.withExecutionState(sExpression([newSnd] + tail))

    if name == SpecialForms.list.value.keyword:
        return handleSpecialFormList(currentFrame)

    if name == SpecialForms.cond.value.keyword:
        return handleSpecialFormCond(currentFrame)

    if name == SpecialForms.handle.value.keyword:
        return handleSpecialFormHandle(currentFrame)

    currentFrame.throwError("Unknown special form (engine bug)")