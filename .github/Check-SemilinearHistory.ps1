Param(
    [Parameter(Mandatory)]
    [string]$targetBranch,
    [Parameter(Mandatory)]
    [string]$sourceBranch
)

$ErrorActionPreference = 'Stop'

$versionBranches = @(
  "main",
  "1.5.6",
  "v1.5.5.x"
)

git fetch origin $targetBranch
$commitTarget = git rev-parse "origin/$targetBranch"
git fetch origin $sourceBranch
$commitSource = git rev-parse "origin/$sourceBranch"

# verify that source branch originates from the latest commit of the target branch
# (i.e. a fast-forward merge could be performed)
git merge-base --is-ancestor $commitTarget $commitSource
if ($LASTEXITCODE -ne "0")
{
   throw "Merge would create a non-semilinear history."
}

# the target branch should only contain simple commits and no merges
$numberOfMergeCommits = git rev-list --min-parents=2 --count "${commitTarget}..${commitSource}"
if ($numberOfMergeCommits -eq "0")
{
    Return
}

$commonError = "Source Branch contains non-linear history. This is only acceptable when merging an older version branch into a newer version. But"

# find the branch that corresponds to the version before
$index = [array]::IndexOf($versionBranches, $targetBranch)
if ($index -eq "-1")
{
    throw "$commonError the Target Branch does not correspond to a release version."
}
$precedingVersionBranch = $versionBranches[$index + 1]
if ($precedingVersionBranch -eq $null)
{
    throw "$commonError there is no preceding version that is allowed to be merged into the Target Branch."
}

# Find the latest commit of the previous Version, that is already merged into the current Verion
git fetch origin $($precedingVersionBranch)
$currentMergeBase = git merge-base "origin/$precedingVersionBranch" "origin/$targetBranch"

# Find the latest commit of the previous Version, that would become part of the current Version after the merge
# This must be a true descendent of the current merge base, otherwise the merge is not merging the changes from the old version into the new version
$newMergeBase = git merge-base "origin/$precedingVersionBranch" "origin/$sourceBranch"

if ($currentMergeBase -eq $newMergeBase)
{
    throw "$commonError the merge into the $targetBranch branch does not include commits from the $precedingVersionBranch branch (merge bases are equal)."
}

git merge-base --is-ancestor $currentMergeBase $newMergeBase
if ($LASTEXITCODE -ne "0")
{
   throw "$commonError the merge into the $targetBranch branch does not include commits from the $precedingVersionBranch branch (merge bases are in the wrong order)."
}
