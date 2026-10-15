param(
    [string]$Profile = "saurus-alpha",
    [string]$Region = "us-east-2",
    [string]$Owner = "jay",
    [string]$AlertEmail = "jay@lebakken.com",
    [int]$MonthlyBudgetUsd = 25,
    [string]$StackName = "saurus-alpha",
    [string]$Aws = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Aws)) {
    $Aws = "aws"
}

Write-Host "Checking AWS identity for profile '$Profile' in $Region..."
& $Aws sts get-caller-identity --profile $Profile --region $Region | Out-Host

Write-Host "Finding default VPC..."
$VpcId = (& $Aws ec2 describe-vpcs `
    --profile $Profile `
    --region $Region `
    --filters Name=is-default,Values=true `
    --query "Vpcs[0].VpcId" `
    --output text)

if (-not $VpcId -or $VpcId -eq "None") {
    throw "No default VPC found in $Region. Create/select a VPC before alpha bootstrap."
}

Write-Host "Finding default VPC subnets..."
$SubnetIds = (& $Aws ec2 describe-subnets `
    --profile $Profile `
    --region $Region `
    --filters Name=vpc-id,Values=$VpcId `
    --query "Subnets[*].SubnetId" `
    --output text) -split "\s+"

$SubnetIds = @($SubnetIds | Where-Object { $_ })
if ($SubnetIds.Count -lt 2) {
    throw "Expected at least two public subnets in $VpcId for the alpha database subnet group."
}

$SubnetCsv = ($SubnetIds -join ",")
Write-Host "Bootstrapping stack '$StackName' in $Region using VPC $VpcId and subnets $SubnetCsv..."
& $Aws cloudformation deploy `
    --profile $Profile `
    --region $Region `
    --template-file infra/aws-alpha/template.yaml `
    --stack-name $StackName `
    --capabilities CAPABILITY_NAMED_IAM `
    --parameter-overrides `
        Owner=$Owner `
        AlertEmail=$AlertEmail `
        MonthlyBudgetUsd=$MonthlyBudgetUsd `
        DeployRegistryService=false `
        VpcId=$VpcId `
        PublicSubnetIds=$SubnetCsv

if ($LASTEXITCODE -ne 0) {
    throw "CloudFormation bootstrap deploy failed for stack '$StackName'. Review stack events before retrying."
}

Write-Host "Bootstrap deploy finished. Stack outputs:"
& $Aws cloudformation describe-stacks `
    --profile $Profile `
    --region $Region `
    --stack-name $StackName `
    --query "Stacks[0].Outputs" `
    --output table
