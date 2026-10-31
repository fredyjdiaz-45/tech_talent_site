<#
Creates the "Recruitment Actions" SharePoint list behind the Recruitment Tracker Power App.
Safe to re-run: existing columns are skipped. Ends by checking every column exists.

Prereqs: PowerShell 7+, PnP.PowerShell (Install-Module PnP.PowerShell -Scope CurrentUser) and an
Entra app for interactive login (README step 1). GCC uses the default cloud; GCC High would add
-AzureEnvironment USGovernmentHigh to Connect-PnPOnline.

Usage: ./provision.ps1 -SiteUrl https://youroig.sharepoint.com/sites/HR -ClientId <app-id-guid>
#>
param(
    [Parameter(Mandatory)] [string] $SiteUrl,
    [Parameter(Mandatory)] [string] $ClientId,
    [string] $ListTitle = "Recruitment Actions"
)
$ErrorActionPreference = "Stop"

$statuses = "Draft", "Pending Approval", "Approved", "Position Prep", "Announcement Open", "Certs Issued",
            "Interviews", "Tentative Offer", "Final Offer / EOD", "Filled", "Cancelled", "Re-recruit"
$offices  = "Front Office", "Audit", "Investigations", "Inspections & Evaluations", "Counsel", "Mission Support"
$recTypes = "Internal (Merit Promotion)", "External (Delegated Examining)", "Both (MP & DE)", "Direct Hire", "Other"

# Internal name, display name, type, choices, default
$fields = @(
    @("Series",            "Series",               "Text"),
    @("Grade",             "Grade",                "Text"),
    @("Office",            "Office",               "Choice", $offices),
    @("DutyLocation",      "Duty Location",        "Text"),
    @("NumVacancies",      "Number of Vacancies",  "Number", $null, "1"),
    @("RecruitmentType",   "Recruitment Type",     "Choice", $recTypes),
    @("AppointmentType",   "Appointment Type",     "Choice", @("Permanent", "Term")),
    @("TermNTE",           "Term NTE Date",        "DateTime"),
    @("FundPermanent",     "Permanent Funds",      "Boolean", $null, "0"),
    @("FundSurge",         "Surge Funds",          "Boolean", $null, "0"),
    @("Reason",            "Reason",               "Choice", @("New Position", "Backfill (Attrition)")),
    @("DepartingEmployee", "Departing Employee",   "Text"),
    @("DepartureDate",     "Departure Date",       "DateTime"),
    @("Justification",     "Justification",        "Note"),
    @("Supervisor",        "Supervisor",           "User"),
    @("Status",            "Status",               "Choice", $statuses, "Draft"),
    @("DateSubmitted",     "Date Submitted",       "DateTime"),
    @("DateApproved",      "Date Approved",        "DateTime"),
    @("ApprovalHistory",   "Approval History",     "Note"),
    @("HRSpecialist",      "HR Specialist",        "User"),
    @("HiringManager",     "Hiring Manager",       "User"),
    @("AnnouncementNo",    "Announcement Number",  "Text"),
    @("AnnouncementOpen",  "Announcement Open",    "DateTime"),
    @("AnnouncementClose", "Announcement Close",   "DateTime"),
    @("Applicants",        "Applicants",           "Number"),
    @("Qualified",         "Qualified",            "Number"),
    @("Referred",          "Referred",             "Number"),
    @("CertsIssued",       "Certs Issued",         "DateTime"),
    @("TentativeOffer",    "Tentative Offer Date", "DateTime"),
    @("FinalOffer",        "Final Offer Date",     "DateTime"),
    @("EODDate",           "EOD Date",             "DateTime"),
    @("PositionsFilled",   "Positions Filled",     "Number"),
    @("OriginalActionID",  "Original Action ID",   "Number"),
    @("Notes",             "Notes",                "Note")
)

function FieldXml($name, $display, $type, $choices = $null, $default = $null) {
    $attrs = switch ($type) {
        "DateTime" { 'Format="DateOnly"' }
        "Note"     { 'NumLines="6" RichText="FALSE"' }
        "Number"   { 'Decimals="0" Min="0"' }
        "User"     { 'UserSelectionMode="PeopleOnly"' }
        default    { '' }
    }
    $inner = ""
    if ($choices) { $inner += "<CHOICES>" + (($choices | ForEach-Object { "<CHOICE>$([Security.SecurityElement]::Escape($_))</CHOICE>" }) -join "") + "</CHOICES>" }
    if ($null -ne $default) { $inner += "<Default>$default</Default>" }
    "<Field ID=""{$([guid]::NewGuid())}"" Type=""$type"" Name=""$name"" StaticName=""$name"" DisplayName=""$([Security.SecurityElement]::Escape($display))"" $attrs>$inner</Field>"
}

Connect-PnPOnline -Url $SiteUrl -Interactive -ClientId $ClientId

if (-not (Get-PnPList -Identity $ListTitle)) {
    New-PnPList -Title $ListTitle -Url "Lists/RecruitmentActions" -Template GenericList -EnableVersioning -OnQuickLaunch | Out-Null
}
# Not required at the list level so Power Automate "Update item" doesn't demand it; the app enforces it.
Set-PnPField -List $ListTitle -Identity "Title" -Values @{ Title = "Position Title"; Required = $false } | Out-Null

$existing = (Get-PnPField -List $ListTitle).InternalName
foreach ($f in $fields) {
    if ($existing -contains $f[0]) { Write-Host "exists: $($f[0])"; continue }
    Add-PnPFieldFromXml -List $ListTitle -FieldXml (FieldXml @f) | Out-Null
    Write-Host "added:  $($f[0])"
}

Set-PnPView -List $ListTitle -Identity "All Items" -Fields "LinkTitle", "Status", "Office", "Grade", "HRSpecialist", "DateSubmitted", "AnnouncementNo", "PositionsFilled" | Out-Null

# Self-check: every column must exist under its intended internal name.
$have = (Get-PnPField -List $ListTitle).InternalName
$missing = $fields | ForEach-Object { $_[0] } | Where-Object { $have -notcontains $_ }
if ($missing) { throw "Missing columns: $($missing -join ', ')" }
Write-Host "OK: '$ListTitle' has all $($fields.Count) columns."
