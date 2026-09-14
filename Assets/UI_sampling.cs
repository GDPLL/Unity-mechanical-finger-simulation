using System.Collections;
using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class UI_sampling : MonoBehaviour
{
    public TextMeshProUGUI textMeshPro;
    public void TextStart()
    {
        textMeshPro.text = "Recording in progress";
        
    }
    public void TextOver()
    {
        textMeshPro.text = "Record completed";
        
    }
    public void StartTraining()
    {
        textMeshPro.text = "Training in progress";   
    }
    public void StartOver()
    {
        textMeshPro.text = "Train completed";
    }
    public void StartTransferring()
    {
         textMeshPro.text = "Recording in Transferring";   
    }
    public void TransferringOver()
    {
        textMeshPro.text = "Transferring completed"; 
        
    }
    public void BluetoothSearching()
    {
        textMeshPro.text = "Searching for Bluetooth...";
    }
    public void BluetoothConnected()
    {
        textMeshPro.text = "Bluetooth connected";
    }
    public void BluetoothFailed()
    {
        textMeshPro.text = "Bluetooth connection failed";
    }
}
