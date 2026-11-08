-- AgentOS WoW native UI shell for the explicitly supported WoW: Forever API.
-- Important: offline-only at this stage. There is NO installed or trusted bridge.
-- No game automation, filesystem access, direct CLI access or credential storage.
local ADDON_NAME = ...
local panel
local statusLine
local answerLine
local questionBox
local askButton
local function setState(message)
    if statusLine then statusLine:SetText(message) end
end
local function createPanel()
    if panel then return panel end
    panel = CreateFrame("Frame", "AgentOSWoWPanel", UIParent, "BackdropTemplate")
    panel:SetSize(445, 280)
    panel:SetPoint("CENTER", UIParent, "CENTER", 0, 0)
    panel:SetMovable(true)
    panel:EnableMouse(true)
    panel:RegisterForDrag("LeftButton")
    panel:SetScript("OnDragStart", panel.StartMoving)
    panel:SetScript("OnDragStop", panel.StopMovingOrSizing)
    panel:SetBackdrop({
        bgFile = "Interface\\Tooltips\\UI-Tooltip-Background",
        edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
        tile = true, tileSize = 16, edgeSize = 16,
        insets = {left = 4, right = 4, top = 4, bottom = 4},
    })
    panel:SetBackdropColor(0.04, 0.08, 0.14, 0.96)
    local title = panel:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    title:SetPoint("TOPLEFT", panel, "TOPLEFT", 16, -17)
    title:SetText("AgentOS")
    local close = CreateFrame("Button", nil, panel, "UIPanelCloseButton")
    close:SetPoint("TOPRIGHT", panel, "TOPRIGHT", -4, -3)
    statusLine = panel:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    statusLine:SetPoint("TOPLEFT", title, "BOTTOMLEFT", 0, -23)
    statusLine:SetWidth(400)
    statusLine:SetJustifyH("LEFT")
    statusLine:SetText("Bridge: not connected | ONE: unknown")
    local label = panel:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    label:SetPoint("TOPLEFT", statusLine, "BOTTOMLEFT", 0, -28)
    label:SetText("Ask AgentOS (read-only; not available until bridge approval)")
    questionBox = CreateFrame("EditBox", nil, panel, "InputBoxTemplate")
    questionBox:SetSize(383, 32)
    questionBox:SetPoint("TOPLEFT", label, "BOTTOMLEFT", 7, -10)
    questionBox:SetAutoFocus(false)
    questionBox:SetMaxLetters(500)
    questionBox:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
    questionBox:Disable()
    askButton = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
    askButton:SetSize(110, 28)
    askButton:SetPoint("TOPLEFT", questionBox, "BOTTOMLEFT", -7, -18)
    askButton:SetText("Send (disabled)")
    askButton:Disable()
    answerLine = panel:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    answerLine:SetWidth(400)
    answerLine:SetJustifyH("LEFT")
    answerLine:SetPoint("TOPLEFT", askButton, "BOTTOMLEFT", 0, -17)
    answerLine:SetText("No live data. The AgentOS local Bridge is not installed or verified.")
    panel:Hide()
    return panel
end
SLASH_AGENTOSWOW1 = "/agentos"
SlashCmdList.AGENTOSWOW = function(command)
    local p = createPanel()
    if p:IsShown() then p:Hide()
    else
        p:Show()
        setState("Bridge: not connected | ONE: unknown")
    end
end
-- No transport handler here by design. Never display 'connected' without verified
-- Node-side session freshness + authorized ONE status evidence.
